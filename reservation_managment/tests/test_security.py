"""
Requests sent by hand (not through the page's buttons) must not give anyone
more power than they have.

`client` is a pytest-django fixture: a fake browser that sends requests to
Django without a real server. `manager_client` (conftest.py) is one logged in
as a manager.
"""

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.urls import reverse

from reservation_managment.models import Booking, User

STRONG_PASSWORD = 'Court-Booking-2026!'

MANAGER_PERMISSIONS = {
    'view_resourcetype',
    'change_resourcetype',
    'view_resource',
    'change_resource',
    'view_availability',
    'add_availability',
    'change_availability',
    'delete_availability',
    'view_booking',
    'view_bookingrequest',
    'view_notification',
}


@pytest.mark.django_db
def test_signup_never_creates_staff_or_superusers(client):
    # An attacker can edit the HTML or send the POST by hand with extra fields.
    # The form only reads the fields in Meta.fields, so these are ignored.
    response = client.post(
        reverse('signup'),
        {
            'username': 'carla',
            'email': 'carla@example.com',
            'password1': STRONG_PASSWORD,
            'password2': STRONG_PASSWORD,
            'is_staff': 'on',
            'is_superuser': 'on',
            'groups': '1',
            'user_permissions': '1',
        },
    )

    assert response.status_code == 302  # The account is still created...
    user = User.objects.get(username='carla')
    assert not user.is_staff  # ...but as a plain customer.
    assert not user.is_superuser
    assert not user.groups.exists()
    assert not user.user_permissions.exists()


@pytest.mark.django_db
def test_managers_group_has_exactly_the_planned_permissions():
    # Created by data migrations 0003 and 0005; catches a permission added by mistake.
    group = Group.objects.get(name='Gestores')

    codenames = set(group.permissions.values_list('codename', flat=True))

    assert codenames == MANAGER_PERMISSIONS


def test_manager_cannot_change_a_booking_with_a_hand_made_post(manager_client, make_booking, at):
    booking = make_booking(at(18), at(19))
    url = reverse('admin:reservation_managment_booking_change', args=[booking.pk])

    response = manager_client.post(url, {'status': Booking.Status.CANCELLED})

    assert response.status_code == 403  # Refused for lack of permission.
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


# ---------------------------------------------------------------------------
# My bookings: a customer only ever reaches their own bookings
# ---------------------------------------------------------------------------
# The page never shows other people's bookings, but anyone can change the id
# in the URL (/bookings/15/cancel/ -> /bookings/16/cancel/) and send the POST.


def test_customer_cannot_cancel_someone_elses_booking(client, other_user, make_booking, at):
    booking = make_booking(at(18), at(19))  # Belongs to `user`.
    client.force_login(other_user)

    response = client.post(reverse('cancel_booking', args=[booking.pk]))

    assert response.status_code == 404  # As if it didn't exist: reveals nothing.
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_customer_cannot_reschedule_someone_elses_booking(client, other_user, make_booking, at):
    booking = make_booking(at(18), at(19))
    client.force_login(other_user)

    response = client.post(
        reverse('reschedule_booking', args=[booking.pk]), {'start': at(20).isoformat()}
    )

    assert response.status_code == 404
    booking.refresh_from_db()
    assert booking.start == at(18)


def test_customer_cannot_book_in_someone_elses_name(client, user, other_user, resource, at):
    # Only staff with "Can add booking" may choose the customer; the field is
    # not even on the page for customers, so this POST is made by hand.
    client.force_login(user)

    response = client.post(
        reverse('book_pay'),
        {'slot': f'{resource.pk}|{at(9).isoformat()}', 'customer': other_user.pk},
    )

    assert response.status_code == 403
    assert not Booking.objects.exists()


def test_customer_search_is_staff_only(client, user):
    # It returns customers' emails, so a customer calling it by hand gets 403.
    client.force_login(user)

    response = client.get(reverse('customer_search'), {'q': 'example.com'})

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Profile: the email (where password reset links go) needs the password
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('password', ['', 'wrong-password'], ids=['missing', 'wrong'])
def test_email_cannot_be_changed_without_the_current_password(client, user, password):
    # Someone at an unattended, logged-in computer tries to take over the account.
    user.email = 'ana@example.com'
    user.save()
    client.force_login(user)

    client.post(
        reverse('profile'),
        {'email': 'attacker@example.com', 'language': 'en', 'current_password': password},
    )

    user.refresh_from_db()
    assert user.email == 'ana@example.com'


# ---------------------------------------------------------------------------
# One account per email
# ---------------------------------------------------------------------------


def test_email_is_unique_in_the_database_ignoring_case(user):
    # Not only the forms: code that skips them, or two sign-ups at the same
    # instant, still can't repeat an email (UNIQUE index, *_ci collation).
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username='copy', email=user.email.upper())
