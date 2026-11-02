"""
Booking notifications: a reschedule is not a new confirmation, and nothing is
emailed unless the booking was really saved.

`django_capture_on_commit_callbacks` is a pytest-django fixture. Each test runs
inside a transaction that is rolled back at the end, so on_commit callbacks
never fire on their own; this fixture captures them and can run them.
"""

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.urls import reverse

from reservation_managment.models import Booking, Notification

Kind = Notification.Kind


def kinds(booking):
    """The notification kinds of a booking, oldest first."""
    return list(booking.notifications.order_by('pk').values_list('kind', flat=True))


def test_rescheduling_creates_a_reschedule_not_a_new_confirmation(make_booking, at):
    booking = make_booking(at(18), at(19))

    booking.start, booking.end = at(20), at(21)
    booking.save()

    assert kinds(booking) == [Kind.BOOKING_CONFIRMED, Kind.BOOKING_RESCHEDULED]


def test_failed_reschedule_creates_no_notification(make_booking, other_user, at):
    make_booking(at(20), at(21), user=other_user)
    booking = make_booking(at(18), at(19))

    booking.start, booking.end = at(20), at(21)  # Already taken.
    with pytest.raises(ValidationError):
        booking.save()

    assert kinds(booking) == [Kind.BOOKING_CONFIRMED]


def test_email_is_not_sent_before_the_transaction_commits(
    make_booking, at, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        booking = make_booking(at(18), at(19))

    assert len(callbacks) == 1  # The email is waiting for the commit...
    assert booking.notifications.get().emailed_at is None  # ...and not sent yet.


def test_a_failed_email_keeps_the_booking_and_is_retried_later(
    make_booking, at, django_capture_on_commit_callbacks, monkeypatch
):
    def brevo_is_down(self, *args, **kwargs):
        raise ConnectionError('Brevo is down')

    with monkeypatch.context() as patch:
        patch.setattr(EmailMessage, 'send', brevo_is_down)
        with django_capture_on_commit_callbacks(execute=True):
            booking = make_booking(at(18), at(19))

    assert Booking.objects.filter(pk=booking.pk).exists()  # The booking stays...
    assert booking.notifications.get().emailed_at is None  # ...and its email is pending.

    call_command('send_pending_emails')  # Brevo is back.

    assert booking.notifications.get().emailed_at is not None
    assert len(mail.outbox) == 1


def test_email_is_in_the_customers_language_not_the_staffs(
    admin_client, user, resource, at, django_capture_on_commit_callbacks
):
    user.language = 'es'
    user.save()

    # The superuser books in Ana's name from the English site.
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(
            reverse('book_pay'),
            {'slot': f'{resource.pk}|{at(9).isoformat()}', 'customer': user.pk},
        )

    (email,) = mail.outbox
    assert email.to == [user.email]
    assert 'Tu reserva está confirmada' in email.subject
