# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import markus
from django_redis import get_redis_connection
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

from django.conf import settings
from django.apps import AppConfig


logger = logging.getLogger("django")


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
            version = ""
            if settings.VERSION_FILE:
                version = settings.VERSION_FILE.get("version", "")
                version = version or settings.VERSION_FILE.get("commit", "")
            version = version or "unknown"

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                release=version,
                send_default_pii=False,
                integrations=[DjangoIntegration()],
                # This prevents Sentry from trying to enable all the auto-enabling
                # integrations. We only want the ones we explicitly set up. This
                # provents sentry from loading the Falcon integration (which fails) in a
                # Django context.
                auto_enabling_integrations=False,
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
