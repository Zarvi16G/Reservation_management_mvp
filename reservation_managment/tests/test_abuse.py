"""
Protections against bots and spam: email verification and rate limits.
They need many requests in a row, or hand-made ones, to show up: exactly
what can't be checked by clicking around.

`mail.outbox` is where Django keeps the emails "sent" during a test.
"""

import pytest
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse

from reservation_managment import ratelimit
from reservation_managment.models import Booking, BookingRequest, User
from reservation_managment.verification import make_token

STRONG_PASSWORD = 'Court-Booking-2026!'


def signup_data(number, **extra):
    return {
        'username': f'player{number}',
        'email': f'player{number}@example.com',
        'password1': STRONG_PASSWORD,
        'password2': STRONG_PASSWORD,
        **extra,
    }


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unverified_customer_cannot_book_even_with_a_hand_made_post(client, resource, at):
    client.post(reverse('signup'), signup_data(1))  # Logged in, email not verified yet.

    response = client.post(reverse('book_pay'), {'slot': f'{resource.pk}|{at(9).isoformat()}'})

    assert response.status_code == 403
    assert not Booking.objects.exists()


@pytest.mark.django_db
def test_signup_sends_a_link_that_verifies_the_email(client):
    client.post(reverse('signup'), signup_data(1))

    (email,) = mail.outbox
    link = next(word for word in email.body.split() if '/accounts/verify/' in word)
    client.get(link)

    assert User.objects.get(username='player1').email_verified


def test_a_link_sent_to_the_old_email_does_not_verify_the_new_one(client, user):
    old_link = reverse('verify_email', args=[make_token(user)])
    user.email, user.email_verified = 'new@example.com', False
    user.save()

    response = client.get(old_link)

    assert response.status_code == 400
    user.refresh_from_db()
    assert not user.email_verified


def test_a_forged_link_does_not_verify(client, user):
    user.email_verified = False
    user.save()
    forged = make_token(user)[:-3] + 'abc'  # The signature no longer matches.

    assert client.get(reverse('verify_email', args=[forged])).status_code == 400


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_is_limited_per_ip(client):
    limit, _period = ratelimit.SIGNUP_PER_IP
    for number in range(limit):
        client.post(reverse('signup'), signup_data(number))
        client.logout()

    response = client.post(reverse('signup'), signup_data(limit))

    assert response.status_code == 429
    assert User.objects.count() == limit


@pytest.mark.django_db
def test_a_bot_filling_the_honeypot_creates_no_account(client):
    client.post(reverse('signup'), signup_data(1, website='https://spam.example'))

    assert not User.objects.exists()


def test_login_locks_after_too_many_failures_even_with_the_right_password(client, user):
    limit, _period = ratelimit.LOGIN_FAILURES_PER_USER_AND_IP
    for _attempt in range(limit):
        client.post(reverse('login'), {'username': 'ana', 'password': 'wrong'})

    response = client.post(reverse('login'), {'username': 'ana', 'password': 'test-pass-123'})

    assert response.status_code == 429  # Even the right password waits: the guessing stops.


def test_password_reset_emails_are_limited_per_email(client, user):
    limit, _period = ratelimit.PASSWORD_RESET_PER_EMAIL
    for _attempt in range(limit + 2):
        response = client.post(reverse('password_reset'), {'email': user.email})

    assert response.status_code == 302  # The usual "check your email" page: reveals nothing...
    assert len(mail.outbox) == limit  # ...but nothing more is sent.


def test_bookings_per_day_are_limited(client, user, make_resource, at):
    court = make_resource()
    BookingRequest.objects.bulk_create(
        [BookingRequest(user=user) for _ in range(ratelimit.BOOKING_REQUESTS_PER_DAY)]
    )
    client.force_login(user)

    client.post(reverse('book_pay'), {'slot': f'{court.pk}|{at(9).isoformat()}'})

    assert not Booking.objects.exists()


def test_a_fake_forwarded_ip_is_ignored_unless_behind_our_proxy(settings):
    # Without Nginx in front, anyone could send this header to get a new "IP" per request.
    request = RequestFactory().get('/', REMOTE_ADDR='203.0.113.7', HTTP_X_FORWARDED_FOR='1.2.3.4')

    settings.USE_X_FORWARDED_FOR = False
    assert ratelimit.client_ip(request) == '203.0.113.7'

    settings.USE_X_FORWARDED_FOR = True  # Production, behind our Nginx.
    assert ratelimit.client_ip(request) == '1.2.3.4'
