import os
from pathlib import Path

# Trust local origins for CSRF (dev)
CSRF_TRUSTED_ORIGINS = [
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    # LAN/IP access (add/remove as you use)
    'http://192.168.29.213',
    'http://192.168.29.213:8000',
    # test client
    'http://testserver',
]

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-spoorthi-secret-key'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.29.213', 'testserver']  # dev-safe; extend in prod

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'companies',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # (optional but recommended)
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'spoorthi_macs.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # needed for role-based UI in templates
                "companies.context_processors.user_header_info",
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'spoorthi_macs.wsgi.application'

#DATABASES = {
    #'default': {
        #'ENGINE': 'django.db.backends.sqlite3',
        #'NAME': BASE_DIR / 'db.sqlite3',
    #}
#}
import pymysql
pymysql.install_as_MySQLdb()
DATABASES = {
     'default': {
         'ENGINE': 'django.db.backends.mysql',
         'NAME': 'sml_db',
         'USER': 'sml_user',
         'PASSWORD': 'Quantum@1234',
         'HOST': '192.168.29.213',
         'PORT': '3306',
         "OPTIONS": {"charset": "utf8mb4"},
     }
}

# --- Cache for login throttling/OTP step-up (used in views.login_view) ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'sml8-login-throttle',
    }
}

# Keep Django’s default backend so Groups/Permissions work with the users
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = []  # keep as-is for dev; add validators in prod

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Align server with dd/mm/yyyy inputs used in modals/Flatpickr
from django.conf.locale.en import formats as en_formats  # noqa: E402
en_formats.DATE_INPUT_FORMATS = ["%d/%m/%Y", "%Y-%m-%d"]
en_formats.DATETIME_INPUT_FORMATS = ["%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "companies/static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # harmless in dev; useful for collectstatic later

# --- Session/Cookie hardening (works in dev; stricter in prod below) ---
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Default session age (two weeks); "remember me" in view can override per-session
SESSION_COOKIE_AGE = 14 * 24 * 3600

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ────────────────────────────────────────────────────────────────────
# SML FEATURE FLAGS & PROVIDERS (SAFE DEFAULTS; PRESERVES EXISTING LOGIC)
# These enable the new modules we added. Set True/False per environment.
# If a feature is OFF or credentials are empty, code paths stay no-op/safe.
# ────────────────────────────────────────────────────────────────────
SML_FEATURES = {
    "CREDIT_BUREAU": True,      # enable API stubs/endpoints for credit score pulls
    "NPA_DASHBOARD": True,      # enable NPA dashboard route/template
    "OFFLINE_KYC": True,        # enable KYCDocument entity (modal/grid)
    "ESCALATION_ALERTS": True,  # enable alert rules + management command
}

SML_CREDIT_BUREAU = {
    "PROVIDER": os.getenv("SML_BUREAU_PROVIDER", "CIBIL").upper(),  # or "CRIF"
    "CIBIL": {
        "BASE_URL": os.getenv("CIBIL_BASE_URL", ""),
        "API_KEY":  os.getenv("CIBIL_API_KEY", ""),
    },
    "CRIF": {
        "BASE_URL": os.getenv("CRIF_BASE_URL", ""),
        "API_KEY":  os.getenv("CRIF_API_KEY", ""),
    },
}

SML_ALERT_CHANNELS = {
    "EMAIL":   {"ENABLED": False, "FROM": os.getenv("ALERT_FROM_EMAIL", ""), "SMTP_URL": os.getenv("ALERT_SMTP_URL", "")},
    "SMS":     {"ENABLED": False, "GATEWAY_URL": os.getenv("ALERT_SMS_URL", ""), "API_KEY": os.getenv("ALERT_SMS_KEY", "")},
    "WEBHOOK": {"ENABLED": False, "URL": os.getenv("ALERT_WEBHOOK_URL", "")},
}

# --- Production-only security (kept no-op under DEBUG=True) ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_CONTENT_TYPE_NOSNIFF = True
