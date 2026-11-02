"""
Data migration: create the "Gestores" (managers) group and its permissions.

Unlike 0001/0002, this one is written by hand: it doesn't change tables, it
inserts rows (a Group and its Permissions), so the group exists in every
database the project is migrated on, production included.

Staff users added to this group can, in the admin:
- view and edit resource types and resources (not create or delete them),
- fully manage opening hours (availabilities),
- only view bookings and notifications.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = 'Gestores'

PERMISSIONS = [
    'view_resourcetype',
    'change_resourcetype',
    'view_resource',
    'change_resource',
    'view_availability',
    'add_availability',
    'change_availability',
    'delete_availability',
    'view_booking',
    'view_notification',
]


def create_managers_group(apps, schema_editor):
    # Django creates permissions *after* all migrations run, so on a brand-new
    # database (like the test one) they don't exist yet. Create them now.
    app_config = apps.get_app_config('reservation_managment')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.set(
        Permission.objects.filter(
            content_type__app_label='reservation_managment',
            codename__in=PERMISSIONS,
        )
    )


def delete_managers_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('reservation_managment', '0002_resource_resourcetype_user_phone_booking_and_more'),
    ]

    operations = [
        migrations.RunPython(create_managers_group, delete_managers_group),
    ]
