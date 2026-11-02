"""
Data migration: let the "Gestores" group view booking requests (read-only,
like bookings). 0003 is already applied, so new permissions go in a new one.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = 'Gestores'
PERMISSION = 'view_bookingrequest'


def add_permission(apps, schema_editor):
    # Same as in 0003: on a new database the permission doesn't exist yet.
    app_config = apps.get_app_config('reservation_managment')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group = Group.objects.get(name=GROUP_NAME)
    group.permissions.add(
        Permission.objects.get(content_type__app_label='reservation_managment', codename=PERMISSION)
    )


def remove_permission(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group:
        group.permissions.remove(*group.permissions.filter(codename=PERMISSION))


class Migration(migrations.Migration):
    dependencies = [
        ('reservation_managment', '0004_booking_requests_and_site_settings'),
    ]

    operations = [
        migrations.RunPython(add_permission, remove_permission),
    ]
