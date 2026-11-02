"""
Email verification: a signed link proves the user owns the email.

The token is the user's id and email, signed with SECRET_KEY (nobody can
forge it) and timestamped (it expires after EMAIL_VERIFICATION_MAX_AGE). It
carries the email, so a link sent to an old email can't verify a new one.
"""

import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from .models import User

logger = logging.getLogger(__name__)

SALT = 'reservation_managment.email-verification'


def make_token(user):
    return signing.dumps({'user': user.pk, 'email': user.email}, salt=SALT)


def user_from_token(token):
    """The user the token was made for, or None if it's forged, expired or outdated."""
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE)
    except signing.BadSignature:  # Includes SignatureExpired.
        return None
    return User.objects.filter(pk=data['user'], email=data['email']).first()


def send_verification_email(request, user):
    """Send the link, in the user's language. Returns False if the email couldn't be sent."""
    with translation.override(user.language):
        link = request.build_absolute_uri(reverse('verify_email', args=[make_token(user)]))
        context = {'user': user, 'link': link}
        subject = render_to_string('registration/verify_email_subject.txt', context).strip()
        body = render_to_string('registration/verify_email.txt', context)
    try:
        send_mail(subject, body, None, [user.email])
    except Exception:  # The account must not break because the mail server failed.
        logger.exception('Could not send the verification email to user %s', user.pk)
        return False
    return True
