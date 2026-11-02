from datetime import datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import ratelimit
from .emails import describe
from .forms import ProfileForm, SignupForm
from .models import (
    BOOKING_CURRENCY,
    BOOKING_PRICE,
    BOOKING_SLOT,
    Booking,
    BookingRequest,
    Resource,
    ResourceType,
    User,
    booking_window,
    get_business_timezone,
)
from .ratelimit import client_ip, hit, is_limited, too_many_requests
from .verification import send_verification_email, user_from_token

# Staff with this permission can book in a customer's name (superuser, or a
# staff account given "Can add booking"). Managers don't have it.
BOOK_FOR_CUSTOMERS = 'reservation_managment.add_booking'
CUSTOMER_SEARCH_MIN_LENGTH = 3
CUSTOMER_SEARCH_MAX_RESULTS = 10


def customer_label(customer):
    """'ana@example.com — Ana Ruiz': the email identifies the customer (it's unique)."""
    name = customer.get_full_name()
    return f'{customer.email} — {name}' if name else customer.email


# Hidden field in the sign-up form: people never see it, bots fill every field.
HONEYPOT_FIELD = 'website'


def signup(request):
    """Create a customer account, log them in and send the email verification link."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == 'POST':
        if request.POST.get(HONEYPOT_FIELD):
            return redirect('home')  # A bot: act as if all went well, create nothing.
        ip = client_ip(request)
        if is_limited('signup', ip, rule=ratelimit.SIGNUP_PER_IP):
            return too_many_requests(request)

        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.language = translation.get_language()  # The language they signed up in.
            user.save()
            hit('signup', ip, rule=ratelimit.SIGNUP_PER_IP)  # Only created accounts count.
            login(request, user)
            _send_verification(request, user)
            return redirect('book')
    else:
        form = SignupForm()

    return render(
        request, 'registration/signup.html', {'form': form, 'honeypot_field': HONEYPOT_FIELD}
    )


def _send_verification(request, user):
    if send_verification_email(request, user):
        messages.info(
            request,
            _('We sent a link to %(email)s. Open it to verify your email and start booking.')
            % {'email': user.email},
        )
    else:
        messages.error(request, _("We couldn't send the verification email. Try again later."))


def verify_email(request, token):
    """The link from the verification email. Works logged in or not."""
    user = user_from_token(token)
    if user is None:
        return render(request, 'registration/verify_email_invalid.html', status=400)
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])
    messages.success(request, _('Your email is verified. You can book now.'))
    return redirect('book' if request.user == user else 'login')


@login_required
@require_POST
def resend_verification(request):
    if request.user.email_verified:
        return redirect('book')
    if hit('verification_email', request.user.pk, rule=ratelimit.VERIFICATION_EMAIL_PER_USER):
        return too_many_requests(request)
    _send_verification(request, request.user)
    return redirect('book')


class LoginView(auth_views.LoginView):
    """
    Django's login, locked for 15 minutes after 10 failed attempts with the same
    username from the same IP (password guessing). Keyed by both, so an
    attacker can't lock a real user out from somewhere else.
    """

    redirect_authenticated_user = True

    def _limit_parts(self):
        return (self.request.POST.get('username', ''), client_ip(self.request))

    def post(self, request, *args, **kwargs):
        rule = ratelimit.LOGIN_FAILURES_PER_USER_AND_IP
        if is_limited('login', *self._limit_parts(), rule=rule):
            return too_many_requests(request)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        hit('login', *self._limit_parts(), rule=ratelimit.LOGIN_FAILURES_PER_USER_AND_IP)
        return super().form_invalid(form)


class PasswordResetView(auth_views.PasswordResetView):
    """
    Django's "forgot your password", limited so nobody can use it to flood an
    inbox: per IP (429) and per email (the usual "check your email" page, but
    nothing is sent, so the page still reveals nothing).
    """

    email_template_name = 'registration/password_reset_email.txt'
    subject_template_name = 'registration/password_reset_subject.txt'

    def form_valid(self, form):
        if hit('password_reset_ip', client_ip(self.request), rule=ratelimit.PASSWORD_RESET_PER_IP):
            return too_many_requests(self.request)
        email = form.cleaned_data['email']
        if hit('password_reset_email', email, rule=ratelimit.PASSWORD_RESET_PER_EMAIL):
            return redirect(self.get_success_url())
        return super().form_valid(form)


@login_required
def profile(request):
    """The logged-in user's own details (the email change needs the password)."""
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            email_changed = 'email' in form.changed_data
            if email_changed:
                user.email_verified = False  # The new address must be verified too.
            user.save()
            # Show the page in the language just chosen: /es/... or /en/...
            with translation.override(user.language):
                messages.success(request, _('Your profile has been updated.'))
                if email_changed:
                    _send_verification(request, user)
                return redirect(reverse('profile'))
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'registration/profile.html', {'form': form})


def email_verified_required(view):
    """Booking pages: customers must verify their email first (staff are exempt)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.can_book:
            return render(request, 'bookings/verify_needed.html', status=403)
        return view(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Booking: slot picker -> checkout (dummy payment) -> result pop-up
# ---------------------------------------------------------------------------


def _slot_value(resource, start):
    """How a slot travels in the form: '<resource id>|<start in ISO format>'."""
    return f'{resource.pk}|{start.isoformat()}'


def _selected_slots(request):
    """The (resource_id, start) pairs ticked in the form. Malformed values are ignored."""
    slots = []
    for value in request.POST.getlist('slot'):
        resource_id, _sep, start = value.partition('|')
        try:
            resource_id, start = int(resource_id), datetime.fromisoformat(start)
        except ValueError:
            continue
        if timezone.is_aware(start):  # Every slot the picker sends carries its time zone.
            slots.append((resource_id, start))
    return slots


def _customer(request):
    """
    Who the booking is for: the logged-in user, or the customer picked by staff.
    Choosing a customer without permission is a forged request: 403.
    """
    customer_id = request.POST.get('customer') or request.GET.get('customer')
    if not customer_id:
        return request.user
    if not request.user.has_perm(BOOK_FOR_CUSTOMERS):
        raise PermissionDenied
    return get_object_or_404(User, pk=customer_id, is_active=True)


@login_required
@email_verified_required
def book(request):
    """The slot picker: the free 1-hour slots of the next 7 days, day by day."""
    tz = get_business_timezone()
    first_day, last_day = booking_window(tz)

    resources = Resource.objects.filter(is_active=True).select_related('resource_type')
    selected_type = request.GET.get('type', '')
    if selected_type.isdigit():
        resources = resources.filter(resource_type_id=selected_type)

    days = []
    for offset in range((last_day - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        rows = []
        for resource in resources:
            slots = [
                {'value': _slot_value(resource, start), 'start': start, 'end': end}
                for start, end in resource.available_slots(day, tz)
            ]
            if slots:
                rows.append({'resource': resource, 'slots': slots})
        days.append({'date': day, 'rows': rows})

    can_book_for_customers = request.user.has_perm(BOOK_FOR_CUSTOMERS)
    # Coming back from the admin or the filter with ?customer=<id>: keep the choice.
    selected_customer = _customer(request) if can_book_for_customers else request.user
    context = {
        'days': days,
        'resource_types': ResourceType.objects.filter(resources__is_active=True).distinct(),
        'selected_type': selected_type,
        'can_book_for_customers': can_book_for_customers,
        'selected_customer': selected_customer if selected_customer != request.user else None,
        'selected_customer_label': (
            customer_label(selected_customer) if selected_customer != request.user else ''
        ),
        # Set by `pay` just before redirecting here; shown once as a pop-up.
        'result': request.session.pop('booking_result', None),
    }
    return render(request, 'bookings/book.html', context)


@login_required
def customer_search(request):
    """
    Customers whose email contains ?q=, for the "Book for customer" search box.
    Only staff who can book for customers may use it: it returns emails.
    """
    if not request.user.has_perm(BOOK_FOR_CUSTOMERS):
        raise PermissionDenied
    query = request.GET.get('q', '').strip()
    if len(query) < CUSTOMER_SEARCH_MIN_LENGTH:
        return JsonResponse({'results': []})

    customers = User.objects.filter(
        is_active=True, is_staff=False, email__icontains=query
    ).order_by('email')[:CUSTOMER_SEARCH_MAX_RESULTS]
    results = [{'id': customer.pk, 'label': customer_label(customer)} for customer in customers]
    return JsonResponse({'results': results})


@login_required
@require_POST
@email_verified_required
def checkout(request):
    """Summary of the selection and the (dummy) payment. Nothing is booked yet."""
    customer = _customer(request)
    slots = _selected_slots(request)
    resources = Resource.objects.in_bulk({resource_id for resource_id, _start in slots})
    selection = [
        (resources[resource_id], start, start + BOOKING_SLOT)
        for resource_id, start in sorted(set(slots))
        if resource_id in resources
    ]
    if not selection:
        messages.error(request, _('Select at least one time slot.'))
        return redirect('book')

    context = {
        'customer': customer,
        'customer_label': customer_label(customer),
        'booking_for_customer': customer != request.user,
        # What will be booked, with back-to-back slots already joined.
        'summary': BookingRequest.join_back_to_back(selection),
        'slot_values': [_slot_value(resource, start) for resource, start, _end in selection],
        'price': BOOKING_PRICE,
        'currency': BOOKING_CURRENCY,
    }
    return render(request, 'bookings/checkout.html', context)


@login_required
@require_POST
@email_verified_required
def pay(request):
    """
    "Pay" and book. The free slots are checked again here (someone may have
    taken one while the customer was paying); the result is shown as a pop-up.
    """
    customer = _customer(request)
    if (
        not request.user.is_staff
        and _booked_today(request.user) >= ratelimit.BOOKING_REQUESTS_PER_DAY
    ):
        messages.error(
            request,
            _('You reached the limit of %(limit)s bookings per day. Try again tomorrow.')
            % {'limit': ratelimit.BOOKING_REQUESTS_PER_DAY},
        )
        return redirect('book')
    result = BookingRequest.create_from_slots(customer, _selected_slots(request))

    request.session['booking_result'] = {
        'confirmed': [describe(booking) for booking in result.confirmed],
        'omitted': [
            describe(Booking(resource=resource, start=start, end=end))
            for resource, start, end in result.omitted
        ],
        'amount': str(result.booking_request.amount_paid) if result.booking_request else None,
        'currency': BOOKING_CURRENCY,
        'reference': result.booking_request.payment_reference if result.booking_request else None,
    }
    # Post/Redirect/Get: reloading the page afterwards doesn't book or pay twice.
    return redirect('book')


def _booked_today(user):
    """Booking requests the user made in the last 24 hours (anti-abuse limit)."""
    since = timezone.now() - timedelta(days=1)
    return user.booking_requests.filter(created_at__gte=since).count()


# ---------------------------------------------------------------------------
# My bookings: list, cancel, reschedule (only the logged-in user's own)
# ---------------------------------------------------------------------------


def _own_booking(request, pk):
    """The booking `pk` if it belongs to the logged-in user; anyone else's is a 404."""
    return get_object_or_404(Booking.objects.select_related('resource'), pk=pk, user=request.user)


@login_required
def my_bookings(request):
    bookings = request.user.bookings.select_related('resource')
    upcoming = bookings.filter(status=Booking.Status.CONFIRMED, start__gt=timezone.now())
    context = {
        'upcoming': upcoming.order_by('start'),
        'history': bookings.exclude(pk__in=upcoming).order_by('-start'),
    }
    return render(request, 'bookings/my_bookings.html', context)


@login_required
@require_POST
def cancel_booking(request, pk):
    booking = _own_booking(request, pk)
    if not booking.can_be_changed:
        messages.error(request, _('This booking can no longer be changed.'))
        return redirect('my_bookings')

    booking.status = Booking.Status.CANCELLED
    booking.save()  # Sends the cancellation email.
    messages.success(request, _('Booking cancelled: %(booking)s') % {'booking': describe(booking)})
    return redirect('my_bookings')


@login_required
def reschedule_booking(request, pk):
    booking = _own_booking(request, pk)
    if not booking.can_be_changed:
        messages.error(request, _('This booking can no longer be changed.'))
        return redirect('my_bookings')

    options = booking.reschedule_options()

    if request.method == 'POST':
        try:
            new_start = datetime.fromisoformat(request.POST.get('start', ''))
        except ValueError:
            new_start = None
        if new_start not in options:
            messages.error(request, _('That time is no longer available. Pick another one.'))
            return redirect('reschedule_booking', pk=booking.pk)

        booking.start, booking.end = new_start, new_start + booking.duration
        try:
            booking.save()  # Validated again under lock; sends the reschedule email.
        except ValidationError:
            messages.error(request, _('That time is no longer available. Pick another one.'))
            return redirect('reschedule_booking', pk=booking.pk)
        messages.success(
            request, _('Booking rescheduled: %(booking)s') % {'booking': describe(booking)}
        )
        return redirect('my_bookings')

    # Group the options by day for the template.
    days = {}
    for start in options:
        days.setdefault(timezone.localtime(start).date(), []).append(start)
    return render(
        request, 'bookings/reschedule.html', {'booking': booking, 'days': sorted(days.items())}
    )
