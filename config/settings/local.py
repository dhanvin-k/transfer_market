from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use PostgreSQL locally via Docker
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'transfer_market',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Email to console during dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
