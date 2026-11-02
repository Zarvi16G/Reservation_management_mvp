"""
Base settings shared by every environment (dev and prod).

Environment-specific settings live in dev.py and prod.py, which import
everything from here and override what they need.

https://docs.djangoproject.com/en/6.1/topics/settings/
"""

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

# config/settings/base.py -> project root is three levels up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')

DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'anymail',  # Sends the emails through Brevo's API.
    'reservation_managment',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # Must be after SessionMiddleware and before CommonMiddleware.
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Pages show times in the zone set in the admin (SiteSettings).
    'reservation_managment.middleware.BusinessTimezoneMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='127.0.0.1'),
        'PORT': env('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Authentication
# https://docs.djangoproject.com/en/6.1/topics/auth/customizing/

AUTH_USER_MODEL = 'reservation_managment.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = env('LANGUAGE_CODE', default='es')

LANGUAGES = [
    ('es', _('Spanish')),
    ('en', _('English')),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

# Fallback only: the real zone is chosen in the admin (Site settings).
TIME_ZONE = env('TIME_ZONE', default='America/Bogota')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
# Your own CSS/JS/images live here while developing.
STATICFILES_DIRS = [BASE_DIR / 'static']
# `collectstatic` copies everything here; the web server serves it in prod.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# User-uploaded files.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

# Real emails go through Brevo's HTTP API (django-anymail), not SMTP: DigitalOcean
# blocks the SMTP ports, and the key can only send (it can't read a mailbox).
# SEND_REAL_EMAILS=False (default) prints them in the runserver console instead.

SEND_REAL_EMAILS = env.bool('SEND_REAL_EMAILS', default=False)

MAILERS = {
    'default': {
        'BACKEND': (
            'anymail.backends.brevo.EmailBackend'
            if SEND_REAL_EMAILS
            else 'django.core.mail.backends.console.EmailBackend'
        ),
    },
}

ANYMAIL = {
    'BREVO_API_KEY': env('BREVO_API_KEY', default=''),
}

# Must be a sender verified in Brevo (Senders, Domains & Dedicated IPs).
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Emails are sent after the request (on_commit, retries), so links can't come
# from the request: this is the site's public address, without a trailing slash.
SITE_URL = env('SITE_URL', default='http://127.0.0.1:8000')


# Login / logout
# https://docs.djangoproject.com/en/6.1/ref/settings/#login-url

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

# Password reset links stop working after 1 hour (Django's default is 3 days).
PASSWORD_RESET_TIMEOUT = 60 * 60

# Email verification links (sent at sign-up and when the email changes).
EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24  # 1 day


# Cache
# Kept in a MySQL table (`python manage.py createcachetable`), so every Gunicorn
# worker shares the same rate-limit counters. No Redis needed.

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    },
}


# Rate limits (reservation_managment/ratelimit.py)
# Behind Nginx, every request comes from Nginx's own IP; the visitor's IP is in
# the X-Forwarded-For header that Nginx adds. Only turn this on behind your
# own proxy: otherwise anyone could send a fake header and dodge the limits.

USE_X_FORWARDED_FOR = env.bool('USE_X_FORWARDED_FOR', default=False)
