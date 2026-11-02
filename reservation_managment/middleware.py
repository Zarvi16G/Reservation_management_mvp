from django.utils import timezone

from .models import get_business_timezone


class BusinessTimezoneMiddleware:
    """
    Show every page (admin included) in the time zone from SiteSettings.
    The booking rules don't depend on this: they call get_business_timezone()
    themselves, so they also work outside requests (shell, tests, commands).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with timezone.override(get_business_timezone()):
            return self.get_response(request)
