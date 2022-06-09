# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import markus
from django_redis import get_redis_connection
from sentry_sdk.integrations.boto3 import Boto3Integration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import ignore_logger

from django.conf import settings
from django.apps import AppConfig

from tecken.libdockerflow import get_release_name
from tecken.libsentry import (
    build_scrub_query_string,
    scrub,
    Scrubber,
    SCRUB_KEYS_DEFAULT,
    set_up_sentry,
)


logger = logging.getLogger("django")


SCRUB_KEYS_TECKEN = [
    # HTTP request bits
    (
        "request.headers",
        ("Auth-Token", "Cookie", "X-Forwarded-For", "X-Real-Ip"),
        scrub,
    ),
    ("request.data", ("csrfmiddlewaretoken", "client_secret"), scrub),
    ("request", ("query_string",), build_scrub_query_string(params=["code", "state"])),
    ("request", ("cookies",), scrub),
    # "request" shows up in exceptions as a repr which in Django includes the
    # query_string, so best to scrub it
    ("exception.values.[].stacktrace.frames.[].vars", ("request",), scrub),
]


class TeckenAppConfig(AppConfig):
    name = "tecken"

    def ready(self):
        # Import our admin site code so it creates the admin site.
        from tecken.base import admin_site  # noqa

        self._configure_markus()
        self._configure_sentry()
        self._fix_default_redis_connection()

    @staticmethod
    def _configure_sentry():
        if settings.SENTRY_DSN:
            release = get_release_name(basedir=settings.BASE_DIR)
            host_id = settings.HOST_ID
            scrubber = Scrubber(scrub_keys=SCRUB_KEYS_DEFAULT + SCRUB_KEYS_TECKEN)

            set_up_sentry(
                release=release,
                host_id=host_id,
                sentry_dsn=settings.SENTRY_DSN,
                integrations=[
                    DjangoIntegration(),
                    Boto3Integration(),
                    RedisIntegration(),
                ],
                before_send=scrubber,
            )

            # Dockerflow logs all unhandled exceptions to request.summary so then Sentry
            # reports it twice
            ignore_logger("request.summary")
            # This warning is unhelpful, so ignore it
            ignore_logger("django.security.DisallowedHost")
        else:
            logger.warning("SENTRY_DSN is not defined. SENTRY is not being set up.")

    @staticmethod
    def _configure_markus():
        markus.configure(settings.MARKUS_BACKENDS)

    @staticmethod
    def _fix_default_redis_connection():
        """For some unknown reason, if you don't do at least one read
        from the Redis connection before you do your first write,
        you can get a `redis.exceptions.ConnectionError` with
        "Error 9 while writing to socket. Bad file descriptor."
        This is only occuring in running unit tests.
        But only do this if the caches['default'] isn't a fake one
        redis_client_class = settings.CACHES['default']['OPTIONS'].get(
           'REDIS_CLIENT_CLASS'
        )
        """
        if "LocMemCache" not in settings.CACHES["default"]["BACKEND"]:
            connection = get_redis_connection("default")
            connection.info()
