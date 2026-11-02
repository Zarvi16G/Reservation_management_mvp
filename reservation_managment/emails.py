"""
Booking notification emails.

Each Notification becomes one email, written from templates/emails/ in the
customer's language and the courts' time zone. Sent after the booking is
committed (transaction.on_commit). If sending fails, the booking stays and the
notification keeps `emailed_at` empty: `python manage.py send_pending_emails`
retries it.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation

logger = logging.getLogger(__name__)


def describe(booking):
    """'Court A — 2026-11-03 18:00-20:00', in the active (business) time zone."""
    start, end = timezone.localtime(booking.start), timezone.localtime(booking.end)
    return f'{booking.resource} — {start:%Y-%m-%d %H:%M}-{end:%H:%M}'


def send_notification_email(notification, bookings=None):
    """
    Send the email for one Notification. Returns True if it was sent.
    For a request summary, `bookings` is the list to report (defaults to the
    request's confirmed bookings, e.g. when retrying).
    """
    # Imported here: models.py imports this module (a circular import otherwise).
    from .models import BOOKING_CURRENCY, Booking, get_business_timezone

    user = notification.user
    if notification.booking_id:
        bookings = [notification.booking]
    elif bookings is None:
        bookings = list(
            notification.booking_request.bookings.filter(status=Booking.Status.CONFIRMED)
        )

    # The customer's language (not the staff member's who booked for them),
    # and the courts' time zone (also when retrying from a command).
    with translation.override(user.language), timezone.override(get_business_timezone()):
        context = {
            'user': user,
            'bookings': bookings,
            'booking_request': notification.booking_request,
            'currency': BOOKING_CURRENCY,
            'my_bookings_url': settings.SITE_URL + reverse('my_bookings'),
        }
        subject = render_to_string(f'emails/{notification.kind}_subject.txt', context)
        body = render_to_string(f'emails/{notification.kind}.txt', context)

    message = EmailMessage(
        subject=' '.join(subject.split()),  # A subject must be a single line.
        body=body,
        to=[user.email],
    )
    try:
        message.send()
    except Exception:  # The booking is already saved; this must not undo it.
        logger.exception('Could not send notification %s; it stays pending', notification.pk)
        return False

    notification.emailed_at = timezone.now()
    notification.save(update_fields=['emailed_at'])
    return True
