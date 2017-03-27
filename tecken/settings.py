# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
Django settings for tecken project.
"""
import os
import subprocess
from datetime import timedelta

from configurations import Configuration, values
from django.contrib.messages import constants as messages
from django.core.urlresolvers import reverse_lazy
from dockerflow.version import get_version
from raven.transport.requests import RequestsHTTPTransport
import django_cache_url


class Constance:
    "Constance settings"
    CONSTANCE_BACKEND = 'constance.backends.redisd.RedisBackend'

    CONSTANCE_REDIS_CONNECTION_CLASS = 'django_redis.get_redis_connection'

    CONSTANCE_CONFIG = {
        'AWS_USE_SPOT_INSTANCES': (
            True,
            'Whether to use spot instances on AWS',
        ),
        'AWS_SPOT_BID_CORE': (
            0.84,
            'The spot instance bid price for the cluster workers',
        ),
        'AWS_EFS_DNS': (
            'fs-616ca0c8.efs.us-west-2.amazonaws.com',  # the current dev instance of EFS
            'The DNS name of the EFS mount for EMR clusters'
        )
    }


class AWS:
    "AWS configuration"

    AWS_CONFIG = {
        # AWS EC2 configuration
        # 'AWS_REGION': 'us-west-2',
        # 'EC2_KEY_NAME': '20161025-dataops-dev',
    }


class CSP:
    # Django-CSP
    CSP_DEFAULT_SRC = (
        "'self'",
    )
    CSP_FONT_SRC = (
        "'self'",
        # 'http://*.mozilla.net',
        # 'https://*.mozilla.net',
        # 'http://*.mozilla.org',
        # 'https://*.mozilla.org',
    )
    CSP_IMG_SRC = (
        "'self'",
        # "data:",
        # 'http://*.mozilla.net',
        # 'https://*.mozilla.net',
        # 'http://*.mozilla.org',
        # 'https://*.mozilla.org',
        # 'https://sentry.prod.mozaws.net',
    )
    CSP_SCRIPT_SRC = (
        "'self'",
        # 'http://*.mozilla.org',
        # 'https://*.mozilla.org',
        # 'http://*.mozilla.net',
        # 'https://*.mozilla.net',
        # 'https://cdn.ravenjs.com',
    )
    CSP_STYLE_SRC = (
        "'self'",
        "'unsafe-inline'",
        # 'http://*.mozilla.org',
        # 'https://*.mozilla.org',
        # 'http://*.mozilla.net',
        # 'https://*.mozilla.net',
    )
    CSP_CONNECT_SRC = (
        "'self'",
        # 'https://sentry.prod.mozaws.net',
    )


class Core(Constance, CSP, AWS, Configuration):
    """Settings that will never change per-environment."""

    # Build paths inside the project like this: os.path.join(BASE_DIR, ...)
    THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(THIS_DIR)

    VERSION = get_version(BASE_DIR)

    # Using the default first site found by django.contrib.sites
    SITE_ID = 1

    INSTALLED_APPS = [
        # Project specific apps
        'tecken.apps.TeckenAppConfig',
        'tecken.symbolicate',
        # 'tecken.clusters',
        # 'atmo.jobs',
        # 'atmo.apps.KeysAppConfig',
        # 'atmo.users',

        # Third party apps
        # 'django_rq',
        # 'allauth',
        # 'allauth.account',
        # 'allauth.socialaccount',
        # 'guardian',
        # 'constance',
        # 'constance.backends.database',
        'dockerflow.django',

        # Django apps
        'django.contrib.sites',
        # 'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
    ]

    MIDDLEWARE_CLASSES = (
        'django.middleware.security.SecurityMiddleware',
        'dockerflow.django.middleware.DockerflowMiddleware',
        'whitenoise.middleware.WhiteNoiseMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'session_csrf.CsrfMiddleware',
        'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'csp.middleware.CSPMiddleware',
    )

    ROOT_URLCONF = 'tecken.urls'

    WSGI_APPLICATION = 'tecken.wsgi.application'

    # set the exponential backoff mechanism of rq-retry
    # def exponential_backoff(tries, base=2):
    #     return ','.join(
    #         [str(pow(base, exponent)) for exponent in range(tries)]
    #     )

    # the total number of tries for each task, 1 regular try + 5 retries
    # RQ_RETRY_MAX_TRIES = 6
    # os.environ['RQ_RETRY_MAX_TRIES'] = str(RQ_RETRY_MAX_TRIES)

    # this needs to be set as an environment variable since that's how rq-retry works
    # os.environ['RQ_RETRY_DELAYS'] = RQ_RETRY_DELAYS = exponential_backoff(RQ_RETRY_MAX_TRIES - 1)

    # Add the django-allauth authentication backend.
    AUTHENTICATION_BACKENDS = (
        'django.contrib.auth.backends.ModelBackend',
        # 'allauth.account.auth_backends.AuthenticationBackend',
        # 'guardian.backends.ObjectPermissionBackend',
    )

    # LOGIN_URL = reverse_lazy('account_login')
    # LOGOUT_URL = reverse_lazy('account_logout')
    # LOGIN_REDIRECT_URL = reverse_lazy('dashboard')

    # django-allauth configuration
    # ACCOUNT_LOGOUT_REDIRECT_URL = LOGIN_REDIRECT_URL
    # ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 7
    # ACCOUNT_EMAIL_SUBJECT_PREFIX = '[Telemetry Analysis Service] '
    # ACCOUNT_EMAIL_REQUIRED = True
    # ACCOUNT_EMAIL_VERIFICATION = 'optional'
    # ACCOUNT_LOGOUT_ON_GET = True
    # ACCOUNT_ADAPTER = 'atmo.users.adapters.AtmoAccountAdapter'
    # ACCOUNT_USERNAME_REQUIRED = False
    # ACCOUNT_USER_DISPLAY = 'atmo.users.utils.email_user_display'

    # SOCIALACCOUNT_ADAPTER = 'atmo.users.adapters.AtmoSocialAccountAdapter'
    # SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'  # no extra verification needed
    # SOCIALACCOUNT_QUERY_EMAIL = True  # needed by the Google provider

    # SOCIALACCOUNT_PROVIDERS = {
    #     'google': {
    #         'HOSTED_DOMAIN': 'mozilla.com',
    #         'AUTH_PARAMS': {
    #             'prompt': 'select_account',
    #         }
    #     }
    # }

    MESSAGE_TAGS = {
        messages.ERROR: 'danger'
    }

    # render the 403.html file
    # GUARDIAN_RENDER_403 = True

    # Internationalization
    # https://docs.djangoproject.com/en/1.9/topics/i18n/
    LANGUAGE_CODE = 'en-us'
    TIME_ZONE = 'UTC'
    USE_I18N = False
    USE_L10N = False
    USE_TZ = True
    DATETIME_FORMAT = 'Y-m-d H:i'  # simplified ISO format since we assume UTC

    STATIC_ROOT = values.Value(default='/opt/static/')
    STATIC_URL = '/static/'
    # STATICFILES_STORAGE = (
    #     'whitenoise.storage.CompressedManifestStaticFilesStorage'
    # )
    # STATICFILES_FINDERS = [
    #     'django.contrib.staticfiles.finders.FileSystemFinder',
    #     'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    #     'npm.finders.NpmFinder',
    # ]
    #
    # NPM_ROOT_PATH = values.Value(default='/opt/npm/')
    # NPM_STATIC_FILES_PREFIX = 'npm'
    # NPM_FILE_PATTERNS = {
    #     'ansi_up': ['ansi_up.js'],
    #     'bootstrap': [
    #         'dist/fonts/*',
    #         'dist/css/*',
    #         'dist/js/bootstrap*.js',
    #     ],
    #     'bootstrap-confirmation2': ['bootstrap-confirmation.min.js'],
    #     'bootstrap-datetime-picker': [
    #         'css/*.css',
    #         'js/*.js',
    #     ],
    #     'clipboard': ['dist/clipboard.min.js'],
    #     'jquery': ['dist/*.js'],
    #     'marked': ['marked.min.js'],
    #     'moment': ['min/moment.min.js'],
    #     'notebookjs': ['notebook.min.js'],
    #     'parsleyjs': ['dist/parsley.min.js'],
    #     'prismjs': [
    #         'prism.js',
    #         'components/*.js',
    #         'plugins/autoloader/*.js',
    #         'themes/prism.css',
    #     ],
    #     'raven-js': [
    #         'dist/raven.*',
    #     ]
    # }

    # the directory to have Whitenoise serve automatically on the
    # root of the URL
    # WHITENOISE_ROOT = os.path.join(THIS_DIR, 'static', 'public')

    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'

    # XXX what IS this?
    SILENCED_SYSTEM_CHECKS = [
        'security.W003',  # We're using django-session-csrf
        # We can't set SECURE_HSTS_INCLUDE_SUBDOMAINS since this runs under a
        # mozilla.org subdomain
        'security.W005',
        'security.W009',  # we know the SECRET_KEY is strong
    ]

    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'OPTIONS': {
                'context_processors': [
                    'django.contrib.auth.context_processors.auth',
                    'django.template.context_processors.debug',
                    'django.template.context_processors.i18n',
                    'django.template.context_processors.media',
                    'django.template.context_processors.static',
                    'django.template.context_processors.tz',
                    'django.template.context_processors.request',
                    'django.contrib.messages.context_processors.messages',
                    'session_csrf.context_processor',
                    # 'atmo.context_processors.settings',
                    # 'atmo.context_processors.version',
                    # 'atmo.context_processors.alerts',
                ],
                'loaders': [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ],
            }
        },
    ]


class Base(Core):
    """Settings that may change per-environment, some with defaults."""

    SECRET_KEY = values.SecretValue()

    DEBUG = values.BooleanValue(default=False)
    DEBUG_PROPAGATE_EXCEPTIONS = values.BooleanValue(default=False)

    ALLOWED_HOSTS = values.ListValue([])

    # The URL under which this instance is running
    SITE_URL = values.URLValue('http://localhost:8000')

    # Database
    # https://docs.djangoproject.com/en/1.9/ref/settings/#databases
    DATABASES = values.DatabaseURLValue('postgres://postgres@db/postgres')

    CACHES = {
        'default': django_cache_url.config(
            default='redis://redis-cache:6379/0',
            env='REDIS_URL',
        ),
        'store': django_cache_url.config(
            default='redis://redis-store:6379/0',
            env='REDIS_STORE_URL',
        )
    }

    LOGGING_USE_JSON = values.BooleanValue(False)

    def LOGGING(self):
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'json': {
                    '()': 'dockerflow.logging.JsonLogFormatter',
                    'logger_name': 'tecken',
                },
                'verbose': {
                    'format': '%(levelname)s %(asctime)s %(name)s %(message)s',
                },
            },
            'handlers': {
                'console': {
                    'level': 'DEBUG',
                    'class': 'logging.StreamHandler',
                    'formatter': (
                        'json' if self.LOGGING_USE_JSON else 'verbose'
                    ),
                },
                'sentry': {
                    'level': 'ERROR',
                    'class': (
                        'raven.contrib.django.raven_compat.handlers'
                        '.SentryHandler'
                    ),
                },
            },
            'loggers': {
                'root': {
                    'level': 'INFO',
                    'handlers': ['sentry', 'console'],
                },
                'django.db.backends': {
                    'level': 'ERROR',
                    'handlers': ['console'],
                    'propagate': False,
                },
                'raven': {
                    'level': 'DEBUG',
                    'handlers': ['console'],
                    'propagate': False,
                },
                'sentry.errors': {
                    'level': 'DEBUG',
                    'handlers': ['console'],
                    'propagate': False,
                },
                'tecken': {
                    'level': 'DEBUG',
                    'handlers': ['console'],
                    'propagate': False,
                },
                'request.summary': {
                    'handlers': ['console'],
                    'level': 'DEBUG',
                    'propagate': False,
                },
            },
        }

    SYMBOL_URLS = values.ListValue([
        'https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.'
        'symbols-public/v1/',
    ])


class Dev(Base):
    """Configuration to be used during development and base class
    for testing"""

    @classmethod
    def post_setup(cls):
        super().post_setup()
        # in case we don't find these AWS config variables in the environment
        # we load them from the .env file
        for param in ('ACCESS_KEY_ID', 'SECRET_ACCESS_KEY', 'DEFAULT_REGION'):
            if param not in os.environ:
                os.environ[param] = values.Value(
                    default='',
                    environ_name=param,
                    environ_prefix='AWS',
                )

    DOTENV = os.path.join(Core.BASE_DIR, '.env')

    @property
    def VERSION(self):
        # XXX needs at least one tag I think
        return {}
        # output = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0'])
        # if output:
        #     return {'version': output.decode().strip()}
        # else:
        #     return {}


class Test(Dev):
    """Configuration to be used during testing"""
    DEBUG = False  # XXX  Why?!

    SECRET_KEY = values.Value('not-so-secret-after-all')

    PASSWORD_HASHERS = (
        'django.contrib.auth.hashers.MD5PasswordHasher',
    )

    MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'


class Stage(Base):
    """Configuration to be used in stage environment"""

    LOGGING_USE_JSON = True

    ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(timedelta(days=365).total_seconds())
    # Mark session and CSRF cookies as being HTTPS-only.
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    # This is needed to get a CRSF token in /admin
    ANON_ALWAYS = True

    @property
    def DATABASES(self):
        "require encrypted connections to Postgres"
        DATABASES = super().DATABASES.value.copy()
        DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'
        return DATABASES

    # Sentry setup
    SENTRY_DSN = values.Value(environ_prefix=None)
    SENTRY_PUBLIC_DSN = values.Value(environ_prefix=None)

    MIDDLEWARE_CLASSES = (
        'raven.contrib.django.raven_compat.middleware'
        '.SentryResponseErrorIdMiddleware',
    ) + Base.MIDDLEWARE_CLASSES

    INSTALLED_APPS = Base.INSTALLED_APPS + [
        'raven.contrib.django.raven_compat',
    ]

    @property
    def RAVEN_CONFIG(self):
        config = {
            'dsn': self.SENTRY_DSN,
            'transport': RequestsHTTPTransport,
        }
        if self.VERSION:
            config['release'] = (
                self.VERSION.get('version') or
                self.VERSION.get('commit') or
                ''
            )
        return config

    # Report CSP reports to this URL that is only available in stage and prod
    CSP_REPORT_URI = '/__cspreport__'

    DOCKERFLOW_CHECKS = [
        'dockerflow.django.checks.check_database_connected',
        'dockerflow.django.checks.check_migrations_applied',
        'dockerflow.django.checks.check_redis_connected',
    ]


class Prod(Stage):
    """Configuration to be used in prod environment"""

    @property
    def CONSTANCE_CONFIG(self):
        config = super().CONSTANCE_CONFIG.copy()
        override = {
            'AWS_EFS_DNS': (
                'fs-d0c30f79.efs.us-west-2.amazonaws.com',  # the current prod instance of EFS
                'The DNS name of the EFS mount for EMR clusters'
            )
        }
        config.update(override)
        return config


class Heroku(Prod):
    """Configuration to be used in prod environment"""
    STATIC_ROOT = os.path.join(Prod.BASE_DIR, 'staticfiles')
    NPM_ROOT_PATH = Prod.BASE_DIR


class Build(Prod):
    """Configuration to be used in build (!) environment"""
    SECRET_KEY = values.Value('not-so-secret-after-all')
