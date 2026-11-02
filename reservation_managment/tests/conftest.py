"""
Fixtures shared by every test in this folder.

pytest finds conftest.py automatically: any test can ask for a fixture just by
using its name as an argument, e.g. `def test_x(resource): ...`.
"""

from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone, translation

from reservation_managment.models import Availability, Booking, Resource, ResourceType, User

OPENING_TIME = time(8, 0)
CLOSING_TIME = time(22, 0)


@pytest.fixture(autouse=True)
def english():
    """Error messages are translatable; check them in English in every test."""
    with translation.override('en'):
        yield


@pytest.fixture
def user(db):
    """A customer with a verified email (so the booking pages let them in)."""
    return User.objects.create_user(
        username='ana', email='ana@example.com', password='test-pass-123', email_verified=True
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username='luis', email='luis@example.com', password='test-pass-123', email_verified=True
    )


@pytest.fixture
def manager(db):
    """A staff user in the "Gestores" group (created by migration 0003)."""
    manager = User.objects.create_user(
        username='gestor', email='gestor@example.com', password='test-pass-123', is_staff=True
    )
    manager.groups.add(Group.objects.get(name='Gestores'))
    return manager


@pytest.fixture
def manager_client(client, manager):
    """A test browser already logged in as `manager`."""
    client.force_login(manager)
    return client


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name='Tennis court')


@pytest.fixture
def booking_day():
    """
    A date 3 days from now: always in the future and inside the 7-day booking
    window (today + 6), whatever time the tests run.
    """
    return timezone.localdate() + timedelta(days=3)


@pytest.fixture
def resource(resource_type, booking_day):
    """A court open 08:00-22:00 on `booking_day`'s weekday (closed other days)."""
    resource = Resource.objects.create(name='Court A', resource_type=resource_type, capacity=4)
    Availability.objects.create(
        resource=resource,
        weekday=booking_day.weekday(),
        start_time=OPENING_TIME,
        end_time=CLOSING_TIME,
    )
    return resource


@pytest.fixture
def at(booking_day):
    """
    Build an aware datetime on `booking_day`: `at(18, 30)` -> 18:30.
    Pass `days=` to move to another day: `at(10, days=1)` -> next day 10:00.
    """

    def build(hour, minute=0, days=0):
        day = booking_day + timedelta(days=days)
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    return build


@pytest.fixture
def make_booking(user, resource):
    """
    Factory: create and save a booking, with `user` and `resource` as defaults.
    `make_booking(start, end)` or `make_booking(start, end, user=other_user)`.
    """

    def build(start, end, **fields):
        fields.setdefault('user', user)
        fields.setdefault('resource', resource)
        booking = Booking(start=start, end=end, **fields)
        booking.save()
        return booking

    return build


@pytest.fixture
def make_past_booking(user, resource, at):
    """
    Factory: insert a confirmed 10:00-11:00 booking one week ago (two weeks
    before `booking_day`, so it's the same weekday and the resource is open).

    save() refuses past bookings, so this uses bulk_create(), which skips save().
    MySQL's bulk_create() doesn't fill in `pk`, so the booking is read back from
    the database before returning it.
    """

    def build():
        start = at(10, days=-14)
        Booking.objects.bulk_create(
            [Booking(user=user, resource=resource, start=start, end=start + timedelta(hours=1))]
        )
        return Booking.objects.get(resource=resource, start=start)

    return build


@pytest.fixture
def make_resource(resource_type):
    """
    Factory: a resource open with the given hours on the given weekdays (all
    7 by default). `make_resource('Court B', hours=[(time(8), time(12))])`.
    """

    def build(name='Court B', hours=((OPENING_TIME, CLOSING_TIME),), weekdays=range(7)):
        resource = Resource.objects.create(name=name, resource_type=resource_type, capacity=4)
        for weekday in weekdays:
            for start_time, end_time in hours:
                resource.availabilities.create(
                    weekday=weekday, start_time=start_time, end_time=end_time
                )
        return resource

    return build


@pytest.fixture
def freeze_now(monkeypatch):
    """
    Pretend the current time is `freeze_now(datetime)`. Django code calls
    timezone.now(), so replacing it changes "now" for the rules being tested.
    """

    def freeze(moment):
        monkeypatch.setattr(timezone, 'now', lambda: moment)

    return freeze
