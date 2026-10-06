from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=None):
    value = os.getenv(name, '')
    if not value.strip():
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]


SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError(
        'SECRET_KEY não definida. Copie .env.example para .env e preencha SECRET_KEY.'
    )

DEBUG = env_bool('DEBUG', default=False)

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
# Host interno do compose para scrape Prometheus → web:8000/metrics
if 'web' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, 'web']

CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django_prometheus',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app_pdv.apps.AppPdvConfig',
    'transporte',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'app_pdv.middleware_observability.RequestObservabilityMiddleware',
    'app_pdv.middleware.LoginProtecaoMiddleware',
    'app_pdv.middleware.SessaoUnicaMiddleware',
    'app_pdv.middleware.BloqueioPagamentoMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'app_pdv.backends.SegurancaAuthBackend',
    'django.contrib.auth.backends.ModelBackend',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

ROOT_URLCONF = 'setup.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app_pdv.context_processors.saas_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'setup.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django_prometheus.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'pdv'),
        'USER': os.getenv('POSTGRES_USER', 'pdv'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_TZ = True
USE_I18N = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'app_pdv/static'),
]
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        # Em DEBUG, serve direto de STATICFILES_DIRS (sem precisar collectstatic a cada CSS).
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else 'whitenoise.storage.CompressedStaticFilesStorage'
        ),
    },
}
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'app_pdv.authentication.SessaoUnicaTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

_cors_origins = env_list('CORS_ALLOWED_ORIGINS')
if DEBUG and not _cors_origins:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = _cors_origins

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=True)
    # Scrapes internos (Prometheus) usam HTTP na rede Docker
    SECURE_REDIRECT_EXEMPT = [r'^metrics/?$']
    # Em HTTP (IP antes do SSL) deixe CSRF_COOKIE_SECURE=False e SESSION_COOKIE_SECURE=False no .env
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', default=True)
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0' if not env_bool('SESSION_COOKIE_SECURE', True) else '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# --- E-mail (contabilidade fiscal, alertas) — mesmas variáveis SMTP_* do Alertmanager ---
DEFAULT_FROM_EMAIL = os.getenv('SMTP_FROM', os.getenv('DEFAULT_FROM_EMAIL', 'noreply@oneirasistemas.com.br'))
SERVER_EMAIL = DEFAULT_FROM_EMAIL
_smtp_host = (os.getenv('SMTP_HOST') or '').strip()
if _smtp_host:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = _smtp_host
    EMAIL_PORT = int(os.getenv('SMTP_PORT', '587') or 587)
    EMAIL_HOST_USER = os.getenv('SMTP_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    EMAIL_USE_TLS = env_bool('SMTP_REQUIRE_TLS', default=True)
    EMAIL_USE_SSL = env_bool('SMTP_USE_SSL', default=False)
else:
    EMAIL_BACKEND = os.getenv(
        'EMAIL_BACKEND',
        'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
    )
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25') or 25)

# --- Fiscal / Focus NFe ---
FOCUS_NFE_API_BASE_HOMOLOGACAO = os.getenv(
    'FOCUS_NFE_API_BASE_HOMOLOGACAO', 'https://homologacao.focusnfe.com.br/v2'
).strip()
FOCUS_NFE_API_BASE_PRODUCAO = os.getenv(
    'FOCUS_NFE_API_BASE_PRODUCAO', 'https://api.focusnfe.com.br/v2'
).strip()
FOCUS_NFE_TIMEOUT_SECONDS = int(os.getenv('FOCUS_NFE_TIMEOUT_SECONDS', '45') or 45)

# --- Observabilidade: logs JSON + nível configurável ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'app_pdv.logging_json.JsonFormatter',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if env_bool('LOG_JSON', default=not DEBUG) else 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'app_pdv.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'app_pdv.fiscal': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'gunicorn.error': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'gunicorn.access': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
