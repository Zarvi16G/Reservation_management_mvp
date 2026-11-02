"""
python manage.py send_test_email you@example.com

Sends one email with the current configuration, to check that Brevo (API key,
verified sender, authorised IP) works before relying on it.
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email to check the email configuration.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Address that receives the test email.')

    def handle(self, *args, **options):
        backend = settings.MAILERS['default']['BACKEND']
        self.stdout.write(f'Backend: {backend}')
        self.stdout.write(f'From:    {settings.DEFAULT_FROM_EMAIL}')
        if not settings.SEND_REAL_EMAILS:
            self.stdout.write(
                self.style.WARNING('SEND_REAL_EMAILS=False: it is printed below, not sent.')
            )

        message = EmailMessage(
            subject='Reservation Management · test email',
            body='If you can read this, the email configuration works.',
            to=[options['to']],
        )
        try:
            message.send()
        except Exception as error:
            # Anymail explains what Brevo rejected (key, sender, IP...).
            raise CommandError(f'The email was not sent: {error}') from error

        if settings.SEND_REAL_EMAILS:
            self.stdout.write(self.style.SUCCESS(f'Sent to {options["to"]} through Brevo.'))
        else:
            self.stdout.write(
                self.style.WARNING('Not sent: set SEND_REAL_EMAILS=True in .env to send it.')
            )
