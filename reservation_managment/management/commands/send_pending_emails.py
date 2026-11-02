"""
python manage.py send_pending_emails

Retries the notifications whose email failed (emailed_at is empty), e.g. if
Brevo was down. Safe to run any time, e.g. every few minutes from cron.
"""

from django.core.management.base import BaseCommand

from reservation_managment.emails import send_notification_email
from reservation_managment.models import Notification


class Command(BaseCommand):
    help = 'Send the notification emails that could not be sent before.'

    def handle(self, *args, **options):
        pending = Notification.objects.filter(emailed_at__isnull=True).select_related(
            'user', 'booking__resource', 'booking_request'
        )
        sent = failed = 0
        for notification in pending:
            if send_notification_email(notification):
                sent += 1
            else:
                failed += 1
        self.stdout.write(f'Sent: {sent} · still pending: {failed}')
