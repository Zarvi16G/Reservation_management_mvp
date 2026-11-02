"""
Production settings: the DigitalOcean droplet.

Every value that changes per server comes from .env on that server.
https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/
"""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# e.g. ALLOWED_HOSTS=example.com,www.example.com,203.0.113.10
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
# e.g. CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS = env('CSRF_TRUSTED_ORIGINS')

# HTTPS. Nginx terminates SSL and forwards this header to gunicorn.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: browsers will only use HTTPS. Start low; raise to 31536000 once stable.
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
