"""
Booking rules (models.py) that can't be checked by clicking around: overlaps,
"now"-dependent rules and the configured time zone.

Fixtures (user, resource, at, make_booking...) come from conftest.py.
"""

import zoneinfo
from datetime import datetime, time

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from reservation_managment.models import Booking, SiteSettings

# ---------------------------------------------------------------------------
# Overlaps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('start', 'end'),
    [
        ((18, 0), (20, 0)),
        ((17, 30), (18, 30)),
        ((19, 30), (20, 30)),
        ((18, 30), (19, 30)),
        ((17, 0), (21, 0)),
    ],
    ids=['same-slot', 'overlaps-start', 'overlaps-end', 'inside', 'contains'],
)
def test_overlapping_booking_is_rejected(make_booking, other_user, at, start, end):
    make_booking(at(18), at(20))

    with pytest.raises(ValidationError, match='already booked'):
        make_booking(at(*start), at(*end), user=other_user)


def test_cancelled_booking_frees_the_slot(make_booking, other_user, at):
    booking = make_booking(at(18), at(19))
    booking.status = Booking.Status.CANCELLED
    booking.save()

    new_booking = make_booking(at(18), at(19), user=other_user)

    assert new_booking.pk is not None


def test_editing_a_booking_does_not_overlap_with_itself(make_booking, at):
    booking = make_booking(at(18), at(19))

    booking.notes = 'Bring rackets'
    booking.save()  # Must not say "already booked" because of its own row.

    booking.refresh_from_db()
    assert booking.notes == 'Bring rackets'


# ---------------------------------------------------------------------------
# Rules that depend on "now"
# ---------------------------------------------------------------------------


def test_booking_in_the_past_is_rejected(make_booking, at):
    with pytest.raises(ValidationError, match='must be in the future'):
        make_booking(at(10, days=-14), at(11, days=-14))


def test_booking_after_the_7_day_window_is_rejected(make_booking, make_resource, at):
    court = make_resource()  # Open every day.

    # booking_day is today + 3, so days=4 is today + 7: one day too far.
    with pytest.raises(ValidationError, match='up to 7 days ahead'):
        make_booking(at(10, days=4), at(11, days=4), resource=court)


def test_booking_that_already_started_cannot_be_rescheduled(make_past_booking, at):
    booking = make_past_booking()

    booking.start, booking.end = at(18), at(19)

    with pytest.raises(ValidationError, match='already started cannot be changed'):
        booking.save()


def test_past_booking_can_still_be_cancelled(make_past_booking):
    booking = make_past_booking()

    booking.status = Booking.Status.CANCELLED
    booking.save()

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert Booking.objects.count() == 1  # Updated in place, not inserted again.


# ---------------------------------------------------------------------------
# Every entry point is validated
# ---------------------------------------------------------------------------


def test_objects_create_also_validates(user, resource, at):
    # Django's create() normally skips clean(); our save() calls full_clean().
    with pytest.raises(ValidationError, match='at least 1 hour'):
        Booking.objects.create(user=user, resource=resource, start=at(10), end=at(10, 30))

    assert not Booking.objects.exists()


# ---------------------------------------------------------------------------
# Time zone (Site settings in the admin)
# ---------------------------------------------------------------------------


def test_opening_hours_are_read_in_the_configured_zone(user, resource, booking_day):
    SiteSettings.objects.create(time_zone='Europe/Madrid')
    madrid = zoneinfo.ZoneInfo('Europe/Madrid')

    # `resource` opens 08:00-22:00, now meaning 08:00-22:00 *Madrid* time.
    def madrid_at(hour):
        return datetime.combine(booking_day, time(hour), tzinfo=madrid)

    Booking(user=user, resource=resource, start=madrid_at(8), end=madrid_at(9)).save()

    late = timezone.make_aware(datetime.combine(booking_day, time(21)))  # 21:00 Bogota...
    with pytest.raises(ValidationError, match='not open at this time'):
        # ...is 03:00/04:00 the next day in Madrid: closed.
        Booking(user=user, resource=resource, start=late, end=late.replace(hour=22)).save()
