# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Django settings for tecken project.
"""

import ast
import logging
import os
import socket

import dj_database_url
from dockerflow.version import get_version
from everett.manager import ConfigManager, ListOf


def dict_parser(val):
    try:
        dict_val = ast.literal_eval(val)
    except SyntaxError as syntax_exc:
        raise ValueError("not a valid Python dict") from syntax_exc

    if not isinstance(dict_val, dict):
        raise ValueError(f"not a valid Python dict: {type(dict_val)}")
    return dict_val


_config = ConfigManager.basic_config()


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(THIS_DIR)

VERSION_FILE = get_version(BASE_DIR)


LOCAL_DEV_ENV = _config(
    "LOCAL_DEV_ENV",
    default="false",
    parser=bool,
    doc="Set to true if you're running in a local dev environment; false otherwise",
)
TEST_ENV = _config(
    "TEST_ENV",
    default="false",
    parser=bool,
    doc="Set to true if you're running tests; false otherwise.",
)
TOOL_ENV = _config(
    "TOOL_ENV",
    default="false",
    parser=bool,
    doc=(
        "Set to true if you're running manage.py in a tool context. For example, for "
        "collectstatic."
    ),
)

if TOOL_ENV:
    # If we're in a tool environment (collecting static files, etc), then we should set
    # fake values in the environment so it doesn't muss up configuration.
    fake_values = [
        ("SECRET_KEY", "fakekey"),
        ("OIDC_RP_CLIENT_ID", "1"),
        ("OIDC_RP_CLIENT_SECRET", "abcdef"),
        ("OIDC_OP_AUTHORIZATION_ENDPOINT", "http://example.com/"),
        ("OIDC_OP_TOKEN_ENDPOINT", "http://example.com/"),
        ("OIDC_OP_USER_ENDPOINT", "http://example.com/"),
        ("DATABASE_URL", "postgresql://postgres:postgres@db/tecken"),
        ("REDIS_URL", "redis://redis-cache:6379/0"),
        ("SYMBOL_URLS", "https://s3.example.com/bucket"),
        ("UPLOAD_DEFAULT_URL", "https://s3.example.com/bucket"),
        ("UPLOAD_TRY_SYMBOLS_URL", "https://s3.example.com/bucket/try/"),
    ]
    for key, val in fake_values:
        os.environ[key] = val


DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

SENTRY_DSN = _config("SENTRY_DSN", default="", doc="Sentry DSN or empty string")

HOSTNAME = _config(
    "HOSTNAME",
    default=socket.gethostname(),
    doc="Unique identifier for the host that is running Tecken. This is used "
    "in logging and metrics. The default is socket.gethostname().",
)

LOGGING_DEFAULT_LEVEL = _config(
    "LOGGING_DEFAULT_LEVEL",
    default="INFO",
    doc="Default level for logging. Should be one of INFO, DEBUG, WARNING, ERROR.",
)


class AddProcessName(logging.Filter):
    process_name = os.environ.get("PROCESS_NAME", "main")

    def filter(self, record):
        record.processname = self.process_name
        return True


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "add_processname": {"()": AddProcessName},
    },
    "formatters": {
        "json": {
            "()": "dockerflow.logging.JsonLogFormatter",
            "logger_name": "tecken",
        },
        "human": {
            "format": "%(levelname)s %(asctime)s - %(processname)s - %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": LOGGING_DEFAULT_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["add_processname"],
        },
        "null": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "django": {
            "level": logging.INFO,
            "handlers": ["console"],
        },
        "django.db.backends": {
            "level": logging.ERROR,
            "handlers": ["console"],
        },
        "django_redis.cache": {
            "level": logging.INFO,
            "handlers": ["console"],
        },
        "django.request": {
            "level": logging.INFO,
            "handlers": ["console"],
        },
        "django.security.DisallowedHost": {
            "handlers": ["null"],
        },
        "fillmore": {
            "level": logging.ERROR,
            "handlers": ["console"],
        },
        "markus": {
            "level": logging.INFO,
            "handlers": ["console"],
        },
        "mozilla_django_oidc": {
            "level": logging.DEBUG,
            "handlers": ["console"],
        },
        "request.summary": {
            "handlers": ["console"],
            "level": logging.INFO,
        },
        "tecken": {
            "level": logging.DEBUG,
            "handlers": ["console"],
        },
    },
}


if LOCAL_DEV_ENV or TEST_ENV or TOOL_ENV:
    LOGGING["handlers"]["console"]["formatter"] = "human"


# Defaulting to 'localhost' here because that's where the Datadog
# agent is expected to run in production.
STATSD_HOST = _config("STATSD_HOST", default="localhost", doc="statsd host.")
STATSD_PORT = _config("STATSD_PORT", default="8125", parser=int, doc="statsd port.")
STATSD_NAMESPACE = _config(
    "STATSD_NAMESPACE", default="", doc="Namespace for statsd keys."
)

MARKUS_BACKENDS = [
    {
        "class": "markus.backends.datadog.DatadogMetrics",
        "options": {
            "statsd_host": STATSD_HOST,
            "statsd_port": STATSD_PORT,
            "statsd_namespace": STATSD_NAMESPACE,
        },
    }
]

if LOCAL_DEV_ENV or TEST_ENV:
    MARKUS_BACKENDS.append({"class": "markus.backends.logging.LoggingMetrics"})


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    # Django apps
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "django.contrib.admin.apps.SimpleAdminConfig",
    "admin_cursor_paginator",
    # Project specific apps
    "tecken.apps.TeckenAppConfig",
    "tecken.base",
    "tecken.download",
    "tecken.upload",
    "tecken.tokens",
    "tecken.api",
    "tecken.useradmin",
    # Third party apps
    "dockerflow.django",
    # Third party apps, that need to be listed last
    "mozilla_django_oidc",
]

# June 2017: Notice that we're NOT adding
# 'mozilla_django_oidc.middleware.RefreshIDToken'. That's because
# most views in this project are expected to be called as AJAX
# or from curl. So it doesn't make sense to require every request
# to refresh the ID token.
# Once there is a way to do OIDC ID token refreshing without needing
# the client to redirect, we can enable that.
# Note also, the ostensible reason for using 'RefreshIDToken' is
# to check that a once-authenticated user is still a valid user.
# So if that's "disabled", that's why we have rather short session
# cookie age.
MIDDLEWARE = [
    "dockerflow.django.middleware.DockerflowMiddleware",
    # 'django.middleware.csrf.CsrfViewMiddleware',
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tecken.tokens.middleware.APITokenAuthenticationMiddleware",
    # Important that this comes after APITokenAuthenticationMiddleware
    "tecken.useradmin.middleware.NotBlockedInAuth0Middleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "tecken.urls"

WSGI_APPLICATION = "tecken.wsgi.application"

# Add the django-allauth authentication backend.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "mozilla_django_oidc.auth.OIDCAuthenticationBackend",
]

if TEST_ENV:
    # Only used for testing to log users in during unit tests
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
DATETIME_FORMAT = "Y-m-d H:i"  # simplified ISO format since we assume UTC

TEMPLATES = [
    # Needed for Django admin
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ],
        },
    },
]

MEDIA_URL = "/media/"

# Root directory for frontend files like index.html
FRONTEND_ROOT = _config(
    "FRONTEND_ROOT",
    default=os.path.join(BASE_DIR, "frontend/build/"),
    doc="Root directory for frontend files like index.html",
)

STATIC_ROOT = _config(
    "STATIC_ROOT",
    default=os.path.join(BASE_DIR, "frontend/build/static/"),
    doc="Root directory for static files.",
)
STATIC_URL = "/static/"

# The default Cache-Control max-age used,
WHITENOISE_MAX_AGE = 60 * 60
WHITENOISE_ALLOW_ALL_ORIGINS = False

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_CACHE_ALIAS = "default"

# System Checks
# Override certain builtin Django system checks because we know
# with confidence we do these good deeds in Nginx.
# https://docs.djangoproject.com/en/1.11/ref/checks/#security
SILENCED_SYSTEM_CHECKS = [
    # Dealt with using Nginx headers
    "security.W001",
    # Dealt with using Nginx headers
    "security.W002",
    # CSRF is explicit only on the views that need it
    "security.W003",
    # We can't set SECURE_HSTS_INCLUDE_SUBDOMAINS since this runs under a
    # mozilla.org subdomain
    "security.W005",
    # Strict-Transport-Security is set in Nginx
    "security.W004",
]

# OIDC setup
OIDC_RP_CLIENT_ID = _config("OIDC_RP_CLIENT_ID", doc="OIDC RP client id.")
OIDC_RP_CLIENT_SECRET = _config("OIDC_RP_CLIENT_SECRET", doc="OIDC RP client secret.")

OIDC_OP_AUTHORIZATION_ENDPOINT = _config(
    "OIDC_OP_AUTHORIZATION_ENDPOINT",
    doc="OIDC OP authorization endpoint.",
)
OIDC_OP_TOKEN_ENDPOINT = _config(
    "OIDC_OP_TOKEN_ENDPOINT",
    doc="OIDC OP token endpoint.",
)
OIDC_OP_USER_ENDPOINT = _config(
    "OIDC_OP_USER_ENDPOINT",
    doc="OIDC OP user endpoint.",
)
OIDC_VERIFY_SSL = _config(
    "OIDC_VERIFY_SSL",
    default="true",
    parser=bool,
    doc=(
        "Whether or not to verify SSL. This should always be True unless in a local "
        "dev environment."
    ),
)

ENABLE_AUTH0_BLOCKED_CHECK = _config(
    "ENABLE_AUTH0_BLOCKED_CHECK",
    default="true",
    parser=bool,
    doc=(
        "Feature flag for the Auth0 Management API check that checks if users are "
        "still valid and not blocked in Auth0's user database."
    ),
)

NOT_BLOCKED_IN_AUTH0_INTERVAL_SECONDS = _config(
    "NOT_BLOCKED_IN_AUTH0_INTERVAL_SECONDS",
    default=str(60 * 60 * 24),
    parser=int,
    doc=(
        "There's a middleware that checks if the user is NOT blocked in "
        "Auth0. But we don't want to do it for every single request, since "
        "it's slowish, so we throttle that check with a cache interval."
    ),
)

# Where users get redirected after successfully signing in
LOGIN_REDIRECT_URL = "/?signedin=true"
LOGIN_REDIRECT_URL_FAILURE = "/?signin=failed"

ENABLE_TOKENS_AUTHENTICATION = _config(
    "ENABLE_TOKENS_AUTHENTICATION",
    default="true",
    parser=bool,
    doc="True if API token authentication is enabled; false otherwise.",
)

# 1 year
TOKENS_DEFAULT_EXPIRATION_DAYS = _config(
    "TOKENS_DEFAULT_EXPIRATION_DAYS",
    default="365",
    parser=int,
    doc="Default expiration in days for tokens.",
)

REDIS_URL = _config("REDIS_URL", doc="URL for Redis.")
REDIS_SOCKET_CONNECT_TIMEOUT = 2
REDIS_SOCKET_TIMEOUT = 2

# This name is hardcoded inside django-redis. It it's set to true in `settings`
# it means that django-redis will attempt WARNING log any exceptions that
# happen with the connection when it swallows the error(s).
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

REDIS_IGNORE_EXCEPTIONS = True

if TOOL_ENV:
    CACHES = {
        "default": {
            "BACKEND": "tecken.libcache.RedisLocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
                "SERIALIZER": "django_redis.serializers.msgpack.MSGPackSerializer",
                "SOCKET_CONNECT_TIMEOUT": REDIS_SOCKET_CONNECT_TIMEOUT,
                "SOCKET_TIMEOUT": REDIS_SOCKET_TIMEOUT,
                "IGNORE_EXCEPTIONS": REDIS_IGNORE_EXCEPTIONS,
            },
        },
    }

CLOUD_SERVICE_PROVIDER = _config(
    "CLOUD_SERVICE_PROVIDER",
    default="AWS",
    doc="The cloud service provider Tecken is using. Either AWS or GCP.",
)

AWS_ACCESS_KEY_ID = _config("AWS_ACCESS_KEY_ID", default="", doc="AWS access key id.")
AWS_SECRET_ACCESS_KEY = _config(
    "AWS_SECRET_ACCESS_KEY", default="", doc="AWS secret access key."
)
AWS_DEFAULT_REGION = _config(
    "AWS_DEFAULT_REGION", default="", doc="AWS default region."
)

S3_CONNECT_TIMEOUT = _config(
    "S3_LOOKUP_CONNECT_TIMEOUT",
    default="5",
    parser=int,
    doc="S3 connection timeout in seconds.",
)
S3_READ_TIMEOUT = _config(
    "S3_LOOKUP_READ_TIMEOUT",
    default="5",
    parser=int,
    doc="S3 read timeout in seconds.",
)


MEMOIZE_KEY_EXISTING_SIZE_SECONDS = _config(
    "MEMOIZE_KEY_EXISTING_SIZE_SECONDS",
    default=str(60 * 60 * 24),
    parser=int,
    doc=(
        "When we ask S3 for the size (if it exists) of a symbol already in S3 "
        "this can be cached. This value determines how long we do that caching."
    ),
)

UPLOAD_FILE_UPLOAD_MAX_WORKERS = _config(
    "UPLOAD_FILE_UPLOAD_MAX_WORKERS",
    default="0",
    parser=int,
    doc=(
        "When we upload a .zip file, we iterate over the content and for each "
        "file within (that isn't immediately ignorable) we kick off a "
        "function which figures out what (and how) to process the file. "
        "That function involves doing a S3 GET (technically ListObjectsV2), "
        "(possible) gzipping the payload and (possibly) a S3 PUT. "
        "All of these function calls get put in a "
        "concurrent.futures.ThreadPoolExecutor pool. This setting is about "
        "how many of these to start, max."
    ),
)

UPLOAD_TEMPDIR = _config(
    "UPLOAD_TEMPDIR",
    default="/tmp/uploads",
    doc="The directory to use as a workspace for handling symbol uploads.",
)
UPLOAD_TEMPDIR_ORPHANS_CUTOFF = _config(
    "UPLOAD_TEMPDIR_ORPHANS_CUTOFF",
    default="15",
    parser=int,
    doc=(
        "Time in minutes before we consider a file to have been orphaned and should "
        "be deleted."
    ),
)

ALLOW_UPLOAD_BY_ANY_DOMAIN = _config(
    "ALLOW_UPLOAD_BY_ANY_DOMAIN",
    default="false",
    parser=bool,
    doc=(
        "When doing local development, especially load testing, it's sometimes "
        "useful to be able to bypass all URL checks for Upload by Download."
    ),
)

SYNCHRONOUS_UPLOAD_FILE_UPLOAD = _config(
    "SYNCHRONOUS_UPLOAD_FILE_UPLOAD",
    default="false",
    parser=bool,
    doc=(
        "This is only really meant for the sake of being overrideable by other "
        "setting classes; in particular when running tests."
    ),
)

SECRET_KEY = _config("SECRET_KEY", doc="Django's secret key for signing things.")

DEBUG = _config(
    "DEBUG",
    default="false",
    parser=bool,
    doc=(
        "Whether or not to enable debug mode. Don't set this to True in server "
        "environments"
    ),
)

ALLOWED_HOSTS = _config(
    "ALLOWED_HOSTS",
    default="",
    parser=ListOf(str),
    doc="Comma-delimited list of strings of host/domain names for this site.",
)

_DATABASE_INFO = _config(
    "DATABASE_URL",
    parser=dj_database_url.parse,
    doc="The database_url to use. This gets parsed into DATABASES configuration.",
)
DATABASES = {"default": _DATABASE_INFO}
CONN_MAX_AGE = _config(
    "CONN_MAX_AGE",
    default="60",
    parser=int,
    doc="Maximum age in minutes for connections.",
)
DATABASES["default"]["CONN_MAX_AGE"] = CONN_MAX_AGE

if not LOCAL_DEV_ENV and not TEST_ENV:
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"


CSRF_FAILURE_VIEW = "tecken.views.csrf_failure"
CSRF_USE_SESSIONS = True

SESSION_COOKIE_AGE = _config(
    "SESSION_COOKIE_AGE",
    default=str(60 * 60 * 24 * 365),
    parser=int,
    doc=(
        "Age in seconds for cookies. Keep it quite short because we don't have a "
        "practical way to do OIDC ID token renewal for this AJAX and curl heavy app."
    ),
)

if not LOCAL_DEV_ENV:
    # Don't enable SSL related things in the local dev environment
    ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
    SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Needed to get a CSRF token in /admin
ANON_ALWAYS = True

DOCKERFLOW_CHECKS = [
    "dockerflow.django.checks.check_database_connected",
    "dockerflow.django.checks.check_migrations_applied",
    "dockerflow.django.checks.check_redis_connected",
    "tecken.libdockerflow.check_storage_urls",
]


SYMBOL_URLS = _config(
    "SYMBOL_URLS",
    parser=ListOf(str),
    doc=(
        "Comma-separated list of urls for symbol downloads.\n\n"
        "Lookups are performed in list order."
    ),
)

UPLOAD_DEFAULT_URL = _config(
    "UPLOAD_DEFAULT_URL",
    doc=(
        "The default url to use for symbol uploads. This must be an item in "
        "SYMBOL_URLS."
    ),
)

UPLOAD_TRY_SYMBOLS_URL = _config(
    "UPLOAD_TRY_SYMBOLS_URL",
    doc=(
        "When an upload comes in with symbols from a Try build, these symbols "
        "mustn't be uploaded with the regular symbols.\n\n"
        "You could set this to UPLOAD_DEFAULT_URL with a '/try' prefix.\n\n"
        "For example::\n\n"
        "    UPLOAD_DEFAULT_URL=http://s3.example.com/publicbucket/\n"
        "    UPLOAD_TRY_SYMBOLS_URL=http://s3.example.com/publicbucket/try/"
    ),
)

# If UPLOAD_DEFAULT_URL is not in SYMBOL_URLS it's just too weird. It means we'd upload
# to a S3 bucket we'd never read from and thus it'd be impossible to know the upload
# worked.
if UPLOAD_DEFAULT_URL not in SYMBOL_URLS:
    raise ValueError(
        f"The UPLOAD_DEFAULT_URL ({UPLOAD_DEFAULT_URL!r}) has to be one of the URLs "
        f"in SYMBOL_URLS ({SYMBOL_URLS!r})"
    )

# The default prefix for locating all symbols
SYMBOL_FILE_PREFIX = _config(
    "SYMBOL_FILE_PREFIX",
    default="v1",
    doc=(
        "Prefix in the bucket for all symbol files. This allows us to change the "
        "file path template."
    ),
)

COMPRESS_EXTENSIONS = _config(
    "COMPRESS_EXTENSIONS",
    default="sym",
    parser=ListOf(str),
    doc=(
        "During upload, for each file in the archive, if the extension "
        "matches this list, the file gets gzip compressed before uploading."
    ),
)

MIME_OVERRIDES = _config(
    "MIME_OVERRIDES",
    default='{"sym":"text/plain"}',
    parser=dict_parser,
    doc=(
        "For specific file uploads, override the mimetype.\n\n"
        "For .sym files, for example, if S3 knows them as 'text/plain' "
        "they become really handy to open in a browser and view directly."
    ),
)

DISALLOWED_SYMBOLS_SNIPPETS = _config(
    "DISALLOWED_SYMBOLS_SNIPPETS",
    # https://bugzilla.mozilla.org/show_bug.cgi?id=1012672
    default="qcom/proprietary",
    parser=ListOf(str),
    doc=(
        "Individual strings that can't be allowed in any of the lines in the "
        "content of a symbols archive file."
    ),
)

# How many uploads to display per page when paginating through
# past uploads.
API_UPLOADS_BATCH_SIZE = 20
API_UPLOADS_CREATED_BATCH_SIZE = 20
API_FILES_BATCH_SIZE = 40

UPLOAD_REATTEMPT_LIMIT_SECONDS = _config(
    "UPLOAD_REATTEMPT_LIMIT_SECONDS",
    default=str(60 * 60 * 12),
    parser=int,
    doc=(
        "Every time we do a symbol upload, we also take a look to see if there "
        "are incomplete uploads that could have failed due to some unlucky "
        "temporary glitch.\n\n"
        "When we do the reattempt, we need to wait sufficiently long because "
        "the upload might just be incomplete because it's in the queue, not "
        "because it failed."
    ),
)

ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = _config(
    "ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS",
    default=(
        "queue.taskcluster.net,firefox-ci-tc.services.mozilla.com,"
        "stage.taskcluster.nonprod.cloudops.mozgcp.net"
    ),
    parser=ListOf(str),
    doc=(
        'When you "upload by download", the URL\'s domain needs to be in this '
        "allow list. This is to double-check that we don't allow downloads from "
        "domains we don't fully trust."
    ),
)

DOWNLOAD_FILE_EXTENSIONS_ALLOWED = _config(
    "DOWNLOAD_FILE_EXTENSIONS_ALLOWED",
    default=".sym,.dl_,.ex_,.pd_,.dbg.gz,.tar.bz2",
    parser=ListOf(str),
    doc=(
        "A list of file extensions that if a file is NOT one of these extensions "
        "we can immediately return 404 and not bother to process for anything "
        "else.\n\n"
        "It's case sensitive and has to be lower case.  As a way to get marginal "
        "optimization of this, make sure '.sym' is first in the list since it's "
        "the most common."
    ),
)
