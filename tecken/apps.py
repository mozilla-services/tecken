# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django_redis import get_redis_connection
from fillmore.libsentry import set_up_sentry
from fillmore.scrubber import (
    Scrubber,
    Rule,
    build_scrub_query_string,
    SCRUB_RULES_DEFAULT,
)
import markus
from sentry_sdk.integrations.boto3 import Boto3Integration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import ignore_logger

from django.conf import settings
from django.apps import AppConfig

from tecken.libdockerflow import get_release_name


logger = logging.getLogger("django")
metrics = markus.get_metrics("tecken")


SCRUB_RULES_TECKEN = [
    # HTTP request bits
    Rule(
        path="request.headers",
        keys=["Auth-Token", "Cookie", "X-Forwarded-For", "X-Real-Ip"],
        scrub="scrub",
    ),
    Rule(
        path="request.data",
        keys=["csrfmiddlewaretoken", "client_secret"],
        scrub="scrub",
    ),
    Rule(
        path="request",
        keys=["query_string"],
        scrub=build_scrub_query_string(params=["code", "state"]),
    ),
    # "request" shows up in exceptions as a repr which in Django includes the
    # query_string, so best to scrub it
    Rule(
        path="exception.values.[].stacktrace.frames.[].vars",
        keys=["request"],
        scrub="scrub",
    ),
]


def count_sentry_scrub_error(msg):
    metrics.incr("sentry_scrub_error", 1)


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
            scrubber = Scrubber(
                rules=SCRUB_RULES_DEFAULT + SCRUB_RULES_TECKEN,
                error_handler=count_sentry_scrub_error,
            )

            set_up_sentry(
                sentry_dsn=settings.SENTRY_DSN,
                release=release,
                host_id=host_id,
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
