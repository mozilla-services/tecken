# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Utilities for using Sentry.

Infrastructure for optionally wrapping things in Sentry contexts to capture
unhandled exceptions.
"""

import logging
import sys

from dockerflow.version import get_version
from raven import Client
from raven.conf import setup_logging
from raven.handlers.logging import SentryHandler
from raven.middleware import Sentry


LOGGER = logging.getLogger(__name__)

# Global Sentry client singleton
_SENTRY_CLIENT = None


class FakeSentryClient:
    """Fake Sentry Client that logs to the logger."""

    def captureMessage(self, msg):
        LOGGER.error("%s", msg)

    def captureException(self):
        LOGGER.exception("captured exception")


def get_sentry_client():
    if _SENTRY_CLIENT:
        return _SENTRY_CLIENT
    else:
        return FakeSentryClient()


def setup_sentry_logging():
    """Set up sentry logging of exceptions."""
    if _SENTRY_CLIENT:
        handler = SentryHandler(_SENTRY_CLIENT)
        handler.setLevel(logging.ERROR)
        setup_logging(handler)


def set_sentry_client(sentry_dsn, basedir):
    """Set a Sentry client using a given sentry_dsn.

    To clear the client, pass in something falsey like ``''`` or ``None``.

    """
    global _SENTRY_CLIENT
    if sentry_dsn:
        version_info = get_version(basedir) or {}
        commit = version_info.get("commit", "")[:8]

        _SENTRY_CLIENT = Client(
            dsn=sentry_dsn, include_paths=["eliot"], tags={"commit": commit}
        )
        LOGGER.info("Set up sentry client")
    else:
        _SENTRY_CLIENT = None
        LOGGER.info("Removed sentry client")


class WSGILoggingMiddleware:
    """WSGI middleware that logs unhandled exceptions."""

    def __init__(self, application):
        # NOTE(willkg): This has to match how the Sentry middleware works so
        # that we can (ab)use that fact and access the underlying application.
        self.application = application

    def __call__(self, environ, start_response):
        """Wrap application in exception capture code."""
        try:
            return self.application(environ, start_response)

        except Exception:
            LOGGER.exception("Unhandled exception")
            exc_info = sys.exc_info()
            start_response(
                "500 Internal Server Error",
                [("content-type", "application/json; charset=utf-8")],
                exc_info,
            )
            return [b'{"msg": "COUGH! Internal Server Error"}']


def wsgi_capture_exceptions(app):
    """Wrap a WSGI app with some kind of unhandled exception capture.

    If a Sentry client is configured, then this will send unhandled exceptions
    to Sentry. Otherwise, it will send them as part of the middleware.

    """
    if _SENTRY_CLIENT is None:
        return WSGILoggingMiddleware(app)
    else:
        return Sentry(app, _SENTRY_CLIENT)
