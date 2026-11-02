"""
Rate limits against bots and spam.

A counter per key (e.g. "signup from this IP") lives in the cache for a fixed
window. When the window ends, the key expires and the count starts again.

    if hit('signup', client_ip(request), rule=SIGNUP_PER_IP):
        return too_many_requests(request)

Limits are combined: by IP (bots creating accounts) and by account or email
(bots that change IP). IP alone isn't enough: bots rotate IPs, and many real
people can share one IP (a university, an office).
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render

MINUTE = 60
HOUR = 60 * MINUTE

# (limit, period in seconds). One place to tune them.
SIGNUP_PER_IP = (5, HOUR)
LOGIN_FAILURES_PER_USER_AND_IP = (10, 15 * MINUTE)
PASSWORD_RESET_PER_EMAIL = (3, HOUR)
PASSWORD_RESET_PER_IP = (10, HOUR)
VERIFICATION_EMAIL_PER_USER = (90, HOUR)
BOOKING_REQUESTS_PER_DAY = 10  # Counted in the database (BookingRequest), not here.


def client_ip(request):
    """The visitor's IP. Behind Nginx, the last address Nginx added to X-Forwarded-For."""
    if settings.USE_X_FORWARDED_FOR:
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '')


def _key(action, *parts):
    """'ratelimit:login:<hash>'. Hashed: no emails or IPs stored in plain text, fixed length."""
    raw = ':'.join(str(part).lower() for part in parts)
    return f'ratelimit:{action}:{hashlib.sha256(raw.encode()).hexdigest()}'


def is_limited(action, *parts, rule):
    """True if `action` for these parts already reached the limit. Doesn't count a new hit."""
    limit, _period = rule
    return cache.get(_key(action, *parts), 0) >= limit


def hit(action, *parts, rule):
    """Count one more `action`. Returns True if this one is over the limit."""
    limit, period = rule
    key = _key(action, *parts)
    cache.add(key, 0, period)  # Starts the window only if the key doesn't exist yet.
    try:
        count = cache.incr(key)
    except ValueError:  # The key expired between add() and incr().
        cache.set(key, 1, period)
        count = 1
    return count > limit


def too_many_requests(request):
    return render(request, '429.html', status=429)
