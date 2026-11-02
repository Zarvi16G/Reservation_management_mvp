import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import payments
from .emails import send_notification_email

# Booking rules.
BOOKING_SLOT = timedelta(hours=1)  # Bookings and opening hours last whole hours.
BOOKING_MIN_DURATION = timedelta(hours=1)
BOOKING_WINDOW_DAYS = 7  # Bookable days: today + the next 6.
BOOKING_PRICE = Decimal('1.00')  # Charged once per request, as a guarantee (dummy payment).
BOOKING_CURRENCY = 'USD'


def is_on_step(value):
    """True if a time/datetime is exactly on :00 or :30."""
    return value.minute in (0, 30) and value.second == 0 and value.microsecond == 0


def is_whole_hours(duration):
    return duration % BOOKING_SLOT == timedelta(0)


def default_time_zone():
    return settings.TIME_ZONE


def validate_time_zone(value):
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
        raise ValidationError(
            _('"%(value)s" is not a valid time zone.'), params={'value': value}
        ) from error


def get_business_timezone():
    """
    The time zone where the courts are. Every booking rule uses it explicitly,
    so the rules behave the same in requests, the shell, tests and commands.
    """
    saved = SiteSettings.objects.filter(pk=SiteSettings.SINGLETON_PK)
    name = saved.values_list('time_zone', flat=True).first()
    return zoneinfo.ZoneInfo(name or settings.TIME_ZONE)


def booking_window(tz):
    """First and last bookable dates (today + 6 days) in the business time zone."""
    today = timezone.localdate(timezone=tz)
    return today, today + timedelta(days=BOOKING_WINDOW_DAYS - 1)


class SiteSettings(models.Model):
    """System-wide settings, editable in the admin. There is only ever one row."""

    SINGLETON_PK = 1

    time_zone = models.CharField(
        _('time zone'),
        max_length=64,
        default=default_time_zone,
        validators=[validate_time_zone],
        help_text=_(
            'Where the courts are. Opening hours and bookings are shown in this zone. '
            'Set it once at the start: changing it later shifts how existing bookings '
            'are displayed.'
        ),
    )

    class Meta:
        verbose_name = _('site settings')
        verbose_name_plural = _('site settings')

    def __str__(self):
        return str(_('Site settings'))

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        settings_row, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return settings_row


class User(AbstractUser):
    """
    Custom user model. Login, password and names come from AbstractUser.
    """

    # Required and unique: it identifies the customer (staff search by email)
    # and receives the booking emails and password reset links. MySQL's
    # *_ci collation compares it case-insensitively, so Ana@x.com == ana@x.com.
    email = models.EmailField(
        _('email address'),
        unique=True,
        error_messages={'unique': _('An account with this email already exists.')},
    )
    phone = models.CharField(_('phone'), max_length=20, blank=True)
    language = models.CharField(
        _('language'),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        help_text=_('Language of the emails this user receives.'),
    )
    email_verified = models.BooleanField(
        _('email verified'),
        default=False,
        help_text=_('Customers must open the link sent to their email before booking.'),
    )

    def clean(self):
        super().clean()
        self.email = self.email.lower()  # Stored in lowercase, whatever form saves it.

    @property
    def can_book(self):
        """Customers need a verified email; staff (employees) are trusted."""
        return self.email_verified or self.is_staff


class ResourceType(models.Model):
    """A category of resource, e.g. "Tennis court" or "Meeting room"."""

    name = models.CharField(_('name'), max_length=100, unique=True)
    description = models.TextField(_('description'), blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('resource type')
        verbose_name_plural = _('resource types')

    def __str__(self):
        return self.name


class Resource(models.Model):
    """Something that can be booked: a specific court or room."""

    name = models.CharField(_('name'), max_length=100)
    resource_type = models.ForeignKey(
        ResourceType,
        on_delete=models.PROTECT,
        related_name='resources',
        verbose_name=_('resource type'),
    )
    description = models.TextField(_('description'), blank=True)
    capacity = models.PositiveIntegerField(
        _('capacity'),
        validators=[MinValueValidator(1)],
        help_text=_('Maximum number of people.'),
    )
    location = models.CharField(_('location'), max_length=200, blank=True)
    image = models.ImageField(_('image'), upload_to='resources/', blank=True)
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_('Inactive resources cannot be booked.'),
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        ordering = ['resource_type__name', 'name']
        verbose_name = _('resource')
        verbose_name_plural = _('resources')

    def __str__(self):
        return self.name

    def opening_intervals(self, date, tz):
        """
        The resource's opening hours on `date` as (start, end) aware datetimes.
        Ranges that touch (08-14 and 14-20) are joined into one (08-20).
        """
        intervals = []
        for availability in self.availabilities.filter(weekday=date.weekday()).order_by(
            'start_time'
        ):
            start = datetime.combine(date, availability.start_time, tzinfo=tz)
            end = datetime.combine(date, availability.end_time, tzinfo=tz)
            if intervals and intervals[-1][1] == start:
                intervals[-1] = (intervals[-1][0], end)
            else:
                intervals.append((start, end))
        return intervals

    def available_slots(self, date, tz=None, ignore=None):
        """
        Free 1-hour slots on `date`, as (start, end) aware datetimes. Leaves out
        slots that are taken, already started, or outside the 7-day window.
        `ignore` is a booking whose own slots count as free (to reschedule it).
        """
        tz = tz or get_business_timezone()
        first_day, last_day = booking_window(tz)
        if not self.is_active or not first_day <= date <= last_day:
            return []

        day_start = datetime.combine(date, time.min, tzinfo=tz)
        taken = list(
            self.bookings.filter(
                status=Booking.Status.CONFIRMED,
                start__lt=day_start + timedelta(days=1),
                end__gt=day_start,
            )
            .exclude(pk=ignore.pk if ignore else None)
            .values_list('start', 'end')
        )
        now = timezone.now()

        slots = []
        for open_at, close_at in self.opening_intervals(date, tz):
            start = open_at
            while start + BOOKING_SLOT <= close_at:
                end = start + BOOKING_SLOT
                is_taken = any(t_start < end and t_end > start for t_start, t_end in taken)
                if start > now and not is_taken:
                    slots.append((start, end))
                start = end
        return slots


class Availability(models.Model):
    """Weekly opening hours of a resource, e.g. Monday 08:00-22:00."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, _('Monday')
        TUESDAY = 1, _('Tuesday')
        WEDNESDAY = 2, _('Wednesday')
        THURSDAY = 3, _('Thursday')
        FRIDAY = 4, _('Friday')
        SATURDAY = 5, _('Saturday')
        SUNDAY = 6, _('Sunday')

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='availabilities',
        verbose_name=_('resource'),
    )
    weekday = models.PositiveSmallIntegerField(_('weekday'), choices=Weekday)
    start_time = models.TimeField(_('start time'))
    end_time = models.TimeField(_('end time'))

    class Meta:
        ordering = ['resource', 'weekday', 'start_time']
        verbose_name = _('availability')
        verbose_name_plural = _('availabilities')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')),
                name='availability_end_after_start',
            ),
        ]

    def __str__(self):
        hours = f'{self.start_time:%H:%M}-{self.end_time:%H:%M}'
        return f'{self.resource} · {self.get_weekday_display()} {hours}'

    def clean(self):
        if self.start_time is None or self.end_time is None:
            return  # The field errors are already reported.

        if self.end_time <= self.start_time:
            raise ValidationError(_('End time must be after start time.'))

        if not (is_on_step(self.start_time) and is_on_step(self.end_time)):
            raise ValidationError(_('Times must be on the hour or half hour (:00 or :30).'))

        some_day = datetime.min
        duration = datetime.combine(some_day, self.end_time) - datetime.combine(
            some_day, self.start_time
        )
        if not is_whole_hours(duration):
            raise ValidationError(_('Opening hours must last whole hours (e.g. 08:30-21:30).'))

        if self.resource_id:
            overlapping = Availability.objects.filter(
                resource_id=self.resource_id,
                weekday=self.weekday,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(_('This time range overlaps another one on the same day.'))


@dataclass
class BookingResult:
    """What BookingRequest.create_from_slots() did with a selection of slots."""

    booking_request: 'BookingRequest | None' = None
    confirmed: list = field(default_factory=list)  # Saved Booking objects.
    omitted: list = field(default_factory=list)  # (resource, start, end) no longer available.


class BookingRequest(models.Model):
    """
    One booking request from the slot picker: the slots a user selected and
    booked together, possibly on several resources and days. It only groups
    the bookings so they get a single summary email, and holds the (dummy)
    payment made to confirm them.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='booking_requests',
        verbose_name=_('user'),
    )
    amount_paid = models.DecimalField(_('amount paid'), max_digits=8, decimal_places=2, default=0)
    payment_reference = models.CharField(_('payment reference'), max_length=32, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('booking request')
        verbose_name_plural = _('booking requests')

    def __str__(self):
        return f'#{self.pk} · {self.user}'

    @classmethod
    def create_from_slots(cls, user, slots):
        """
        Book the selected 1-hour slots, given as (resource_id, start) pairs.

        Slots that are no longer free (someone took them in the meantime) or
        that were never valid are skipped and reported in `omitted`; the rest
        is booked. Back-to-back slots on the same resource become one booking.
        BOOKING_PRICE is charged once, only if something was booked.
        """
        tz = get_business_timezone()
        requested = sorted(set(slots), key=lambda slot: (slot[0], slot[1]))
        result = BookingResult()

        with transaction.atomic():
            # Lock every resource involved (in a fixed order, to avoid deadlocks),
            # then check what's free. Nobody else can book them until we commit.
            resource_ids = {resource_id for resource_id, _start in requested}
            locked = Resource.objects.select_for_update().filter(pk__in=resource_ids).order_by('pk')
            resources = {resource.pk: resource for resource in locked}

            free_slots = {}  # (resource_id, date) -> set of free slot starts
            accepted = []  # (resource, start, end)
            for resource_id, start in requested:
                resource = resources.get(resource_id)
                if resource is None:
                    continue  # Unknown resource: a forged request; nothing to report.
                end = start + BOOKING_SLOT
                date = timezone.localtime(start, tz).date()
                key = (resource_id, date)
                if key not in free_slots:
                    free_slots[key] = {s for s, _e in resource.available_slots(date, tz)}
                if start in free_slots[key]:
                    accepted.append((resource, start, end))
                else:
                    result.omitted.append((resource, start, end))

            if not accepted:
                return result

            booking_request = cls.objects.create(user=user)
            for resource, start, end in cls.join_back_to_back(accepted):
                booking = Booking(
                    user=user,
                    resource=resource,
                    start=start,
                    end=end,
                    booking_request=booking_request,
                )
                try:
                    with transaction.atomic():  # A savepoint: undo only this booking on error.
                        booking.save()
                except ValidationError:
                    result.omitted.append((resource, start, end))
                else:
                    result.confirmed.append(booking)

            if not result.confirmed:
                booking_request.delete()
                return result

            booking_request.amount_paid = BOOKING_PRICE
            booking_request.payment_reference = payments.charge(BOOKING_PRICE, BOOKING_CURRENCY)
            booking_request.save(update_fields=['amount_paid', 'payment_reference'])

            result.booking_request = booking_request
            notification = Notification.objects.create(
                user=user,
                booking_request=booking_request,
                kind=Notification.Kind.REQUEST_CONFIRMED,
            )
            confirmed = list(result.confirmed)
            transaction.on_commit(lambda: send_notification_email(notification, confirmed))

        return result

    @staticmethod
    def join_back_to_back(slots):
        """[(court, 9, 10), (court, 10, 11)] -> [(court, 9, 11)]. Expects sorted input."""
        joined = []
        for resource, start, end in slots:
            if joined and joined[-1][0] == resource and joined[-1][2] == start:
                joined[-1] = (resource, joined[-1][1], end)
            else:
                joined.append((resource, start, end))
        return joined


class Booking(models.Model):
    """A user's reservation of a resource for a time range."""

    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', _('Confirmed')
        CANCELLED = 'cancelled', _('Cancelled')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('user'),
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('resource'),
    )
    booking_request = models.ForeignKey(
        BookingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings',
        verbose_name=_('booking request'),
        help_text=_('Empty for bookings made one by one (e.g. in the admin).'),
    )
    start = models.DateTimeField(_('start'))
    end = models.DateTimeField(_('end'))
    status = models.CharField(
        _('status'),
        max_length=10,
        choices=Status,
        default=Status.CONFIRMED,
    )
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        ordering = ['-start']
        verbose_name = _('booking')
        verbose_name_plural = _('bookings')
        indexes = [
            models.Index(fields=['resource', 'start']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F('start')),
                name='booking_end_after_start',
            ),
        ]

    def __str__(self):
        start = timezone.localtime(self.start)
        return f'{self.resource} · {start:%Y-%m-%d %H:%M} ({self.user})'

    def save(self, *args, notify=True, **kwargs):
        with transaction.atomic():
            # Lock the resource row so two people booking the same resource at
            # the same moment are validated one after the other, never both at once.
            Resource.objects.select_for_update().get(pk=self.resource_id)
            self.full_clean()
            saved = self._saved_state()  # Read before saving, to compare old vs new.
            super().save(*args, **kwargs)

            kind = self._notification_kind(saved)
            # A new booking inside a request is announced by the request's summary email.
            in_request_summary = saved is None and self.booking_request_id
            if kind and notify and not in_request_summary:
                notification = Notification.objects.create(user=self.user, booking=self, kind=kind)
                # Email only once the booking is really in the database. If the
                # transaction fails, no email is sent; if the email fails, the booking stays.
                transaction.on_commit(lambda: send_notification_email(notification))

    @property
    def duration(self):
        return self.end - self.start

    @property
    def can_be_changed(self):
        """Customers can cancel or reschedule a confirmed booking until it starts."""
        return self.status == self.Status.CONFIRMED and self.start > timezone.now()

    def reschedule_options(self, tz=None):
        """
        Start times this booking could move to, inside the 7-day window: same
        resource, same length, every hour free. Its own slots count as free.
        """
        tz = tz or get_business_timezone()
        first_day, last_day = booking_window(tz)
        hours = self.duration // BOOKING_SLOT
        options = []
        for offset in range((last_day - first_day).days + 1):
            day = first_day + timedelta(days=offset)
            free = {start for start, _end in self.resource.available_slots(day, tz, ignore=self)}
            for start in sorted(free):
                fits = all(start + BOOKING_SLOT * hour in free for hour in range(hours))
                if fits and start != self.start:
                    options.append(start)
        return options

    def _saved_state(self):
        """This booking's status/start/end as stored in the database, or None if it's new."""
        if self.pk is None:
            return None
        return Booking.objects.filter(pk=self.pk).values('status', 'start', 'end').first()

    def _notification_kind(self, saved):
        """Which notification (if any) this save should trigger, given the previous state."""
        is_confirmed = self.status == self.Status.CONFIRMED

        if saved is None or saved['status'] == self.Status.CANCELLED:
            # A new booking, or a cancelled one confirmed again.
            return Notification.Kind.BOOKING_CONFIRMED if is_confirmed else None
        if not is_confirmed:
            return Notification.Kind.BOOKING_CANCELLED
        if (saved['start'], saved['end']) != (self.start, self.end):
            return Notification.Kind.BOOKING_RESCHEDULED
        return None  # e.g. only the notes changed.

    def clean(self):
        if self.start is None or self.end is None or not self.resource_id:
            return  # The field errors are already reported.

        tz = get_business_timezone()

        # Time range: :00 or :30, at least 1 hour, in whole hours.
        if self.end <= self.start:
            raise ValidationError({'end': _('End must be after start.')})

        start = timezone.localtime(self.start, tz)
        end = timezone.localtime(self.end, tz)

        if not (is_on_step(start) and is_on_step(end)):
            raise ValidationError(_('Bookings must start and end on :00 or :30.'))

        if self.duration < BOOKING_MIN_DURATION:
            raise ValidationError(_('A booking must last at least 1 hour.'))

        if not is_whole_hours(self.duration):
            raise ValidationError(_('A booking must last whole hours (1h, 2h, 3h...).'))

        # A cancelled booking doesn't hold the slot, so the rest doesn't apply.
        if self.status == self.Status.CANCELLED:
            return

        # The time rules apply when the booking takes a time slot: when it's new,
        # rescheduled or confirmed again. Editing only the notes of an old booking is fine.
        saved = self._saved_state()
        takes_new_slot = (
            saved is None
            or saved['status'] == self.Status.CANCELLED
            or (saved['start'], saved['end']) != (self.start, self.end)
        )
        if takes_new_slot:
            if saved is not None and saved['start'] <= timezone.now():
                raise ValidationError(_('A booking that has already started cannot be changed.'))
            if self.start <= timezone.now():
                raise ValidationError({'start': _('Bookings must be in the future.')})
            _first_day, last_day = booking_window(tz)
            if start.date() > last_day:
                raise ValidationError(
                    {
                        'start': _('Bookings can only be made up to %(days)s days ahead.')
                        % {'days': BOOKING_WINDOW_DAYS}
                    }
                )

        if not self.resource.is_active:
            raise ValidationError({'resource': _('This resource is not available for booking.')})

        # Inside the resource's opening hours, on a single day.
        fits_availability = start.date() == end.date() and any(
            open_at <= start and end <= close_at
            for open_at, close_at in self.resource.opening_intervals(start.date(), tz)
        )
        if not fits_availability:
            raise ValidationError(_('The resource is not open at this time.'))

        # No overlap with another confirmed booking on the same resource.
        overlapping = Booking.objects.filter(
            resource_id=self.resource_id,
            status=self.Status.CONFIRMED,
            start__lt=self.end,
            end__gt=self.start,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError(_('This time slot is already booked.'))


class Notification(models.Model):
    """
    A record of each email sent to a user: about one booking, or a summary
    of a whole booking request (never both).

    `user` is the recipient, stored explicitly so "only show a user their own
    notifications" is a simple filter.
    """

    class Kind(models.TextChoices):
        BOOKING_CONFIRMED = 'booking_confirmed', _('Booking confirmed')
        BOOKING_CANCELLED = 'booking_cancelled', _('Booking cancelled')
        BOOKING_RESCHEDULED = 'booking_rescheduled', _('Booking rescheduled')
        REQUEST_CONFIRMED = 'request_confirmed', _('Booking request confirmed')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('user'),
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name=_('booking'),
    )
    booking_request = models.ForeignKey(
        BookingRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name=_('booking request'),
    )
    kind = models.CharField(_('kind'), max_length=30, choices=Kind)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    emailed_at = models.DateTimeField(
        _('emailed at'),
        null=True,
        blank=True,
        help_text=_('Empty means the email has not been sent yet.'),
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        constraints = [
            # About one booking OR one request: exactly one of the two is set.
            models.CheckConstraint(
                condition=(
                    models.Q(booking__isnull=False, booking_request__isnull=True)
                    | models.Q(booking__isnull=True, booking_request__isnull=False)
                ),
                name='notification_booking_xor_request',
            ),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} · {self.user}'
