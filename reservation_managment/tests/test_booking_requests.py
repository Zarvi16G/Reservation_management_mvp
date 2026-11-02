"""
Booking a selection of slots in one go (BookingRequest.create_from_slots).

A selection is a list of (resource_id, start) pairs, like the slot picker will
send. Free slots are booked (back-to-back ones joined), the rest is reported
as omitted, and the user gets one summary email.
"""

import threading
from datetime import datetime, time

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone

from reservation_managment.models import Booking, BookingRequest, Notification, User

Kind = Notification.Kind


@pytest.fixture
def book(user):
    """`book([(resource, start), ...])` -> BookingResult."""

    def run(selection, as_user=None):
        slots = [(resource.pk, start) for resource, start in selection]
        return BookingRequest.create_from_slots(as_user or user, slots)

    return run


# ---------------------------------------------------------------------------
# Several people booking the same slot at the same moment
# ---------------------------------------------------------------------------


# transaction=True: each thread needs its own real, committed transaction.
# serialized_rollback=True: restores the "Gestores" group afterwards, because
# this kind of test empties every table when it ends.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_three_users_booking_the_same_slot_at_once_only_one_wins(resource, at):
    players = [
        User.objects.create_user(username=f'player{n}', email=f'player{n}@example.com')
        for n in range(3)
    ]
    start_line = threading.Barrier(len(players))  # Releases all threads together.
    results, errors = [], []

    def try_to_book(player):
        try:
            start_line.wait()
            results.append(BookingRequest.create_from_slots(player, [(resource.pk, at(9))]))
        except Exception as error:  # Reported by the assert below.
            errors.append(error)
        finally:
            connection.close()  # Each thread opened its own database connection.

    threads = [threading.Thread(target=try_to_book, args=(player,)) for player in players]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert Booking.objects.count() == 1  # No double booking.
    assert sorted(len(result.confirmed) for result in results) == [0, 0, 1]
    assert sorted(len(result.omitted) for result in results) == [0, 1, 1]


def test_slot_taken_in_the_meantime_is_omitted_and_the_rest_booked(
    book, resource, make_booking, other_user, at
):
    # The user loaded the page with 09-12 free, then someone took 10:00-11:00.
    make_booking(at(10), at(11), user=other_user)

    result = book([(resource, at(9)), (resource, at(10)), (resource, at(11))])

    assert [(b.start, b.end) for b in result.confirmed] == [(at(9), at(10)), (at(11), at(12))]
    assert result.omitted == [(resource, at(10), at(11))]


# ---------------------------------------------------------------------------
# Joining slots and the free slots of today
# ---------------------------------------------------------------------------


def test_back_to_back_slots_become_one_booking(book, resource, at):
    result = book([(resource, at(9)), (resource, at(10)), (resource, at(11))])

    (booking,) = result.confirmed
    assert (booking.start, booking.end) == (at(9), at(12))


def test_today_only_shows_slots_that_have_not_started(make_resource, freeze_now):
    court = make_resource()  # Open every day, 08-22.
    today = timezone.localdate()
    freeze_now(timezone.make_aware(datetime.combine(today, time(10, 15))))

    first_start, _end = court.available_slots(today)[0]

    assert timezone.localtime(first_start).time() == time(11)  # 10:00 started at 10:15.


# ---------------------------------------------------------------------------
# The summary email
# ---------------------------------------------------------------------------


def test_one_summary_email_listing_only_confirmed_bookings(
    book, resource, make_booking, other_user, user, at, django_capture_on_commit_callbacks
):
    make_booking(at(10), at(11), user=other_user)

    with django_capture_on_commit_callbacks(execute=True):
        book([(resource, at(9)), (resource, at(10)), (resource, at(11))])

    (email,) = mail.outbox  # One email for the whole request.
    assert email.to == [user.email]
    assert '09:00–10:00' in email.body
    assert '11:00–12:00' in email.body
    assert '10:00–11:00' not in email.body  # Omitted, so not in the email.
    assert Notification.objects.get(kind=Kind.REQUEST_CONFIRMED).emailed_at is not None
