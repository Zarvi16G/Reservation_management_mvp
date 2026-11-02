import zoneinfo

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from .models import (
    Availability,
    Booking,
    BookingRequest,
    Notification,
    Resource,
    ResourceType,
    SiteSettings,
    User,
)


class SiteSettingsForm(forms.ModelForm):
    # A dropdown of every zone the server knows, instead of free text.
    time_zone = forms.ChoiceField(
        label=_('Time zone'),
        choices=[(name, name) for name in sorted(zoneinfo.available_timezones())],
    )

    class Meta:
        model = SiteSettings
        fields = ['time_zone']


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Only superusers can see it (managers have no permission on this model)."""

    form = SiteSettingsForm

    def changelist_view(self, request, extra_context=None):
        # Check permissions first: Django's own check runs inside the view we skip.
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        # There is only one row: go straight to its edit page.
        site_settings = SiteSettings.load()
        return redirect('admin:reservation_managment_sitesettings_change', site_settings.pk)

    def has_add_permission(self, request):
        return False  # The single row is created by SiteSettings.load().

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (_('Contact'), {'fields': ('phone', 'language', 'email_verified')}),
    )
    list_display = ('username', 'email', 'email_verified', 'first_name', 'last_name', 'is_staff')
    # "Add user" asks for the email too (Django's default only asks username/password).
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('username', 'email', 'usable_password', 'password1', 'password2'),
            },
        ),
    )


@admin.register(ResourceType)
class ResourceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class AvailabilityInline(admin.TabularInline):
    """Edit a resource's opening hours on the resource's own page."""

    model = Availability
    extra = 1


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource_type', 'capacity', 'location', 'is_active')
    list_filter = ('resource_type', 'is_active')
    search_fields = ('name', 'location')
    inlines = [AvailabilityInline]


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('resource', 'weekday', 'start_time', 'end_time')
    list_filter = ('weekday', 'resource')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('resource', 'user', 'start', 'end', 'status', 'booking_request')
    list_filter = ('status', 'resource__resource_type', 'resource')
    search_fields = ('user__username', 'user__email', 'resource__name')
    date_hierarchy = 'start'
    autocomplete_fields = ('user', 'resource')
    readonly_fields = ('booking_request', 'created_at')

    def add_view(self, request, form_url='', extra_context=None):
        # New bookings are made with the slot picker (free slots only, same
        # rules and emails as customers), where staff choose the customer.
        if not self.has_add_permission(request):
            raise PermissionDenied
        return redirect('book')


class RequestBookingInline(admin.TabularInline):
    """The bookings of a request, listed on the request's page (read-only)."""

    model = Booking
    fields = ('resource', 'start', 'end', 'status')
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    """Read-only: requests are created by the slot picker, never by hand."""

    list_display = ('__str__', 'user', 'amount_paid', 'payment_reference', 'created_at')
    search_fields = ('user__username', 'user__email', 'payment_reference')
    readonly_fields = ('user', 'amount_paid', 'payment_reference', 'created_at')
    inlines = [RequestBookingInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Read-only: notifications are created by Booking/BookingRequest, never by hand."""

    list_display = ('kind', 'user', 'booking', 'booking_request', 'created_at', 'emailed_at')
    list_filter = ('kind',)
    search_fields = ('user__username', 'user__email')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
