# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Utilities for using Sentry.

Infrastructure for optionally wrapping things in Sentry contexts to capture
unhandled exceptions.
"""

import logging

from dockerflow.version import get_version
import sentry_sdk
from sentry_sdk.integrations.falcon import FalconIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


LOGGER = logging.getLogger(__name__)


def get_release(basedir):
    version_info = get_version(basedir)

    if version_info:
        tag = version_info.get("tag", "none")

        commit = version_info.get("commit")
        commit = commit[:8] if commit else "unknown"

        return f"{tag}:{commit}"
    return "unknown"


def setup_sentry(basedir, host_id, sentry_dsn):
    """Set up Sentry with Falcon

    https://docs.sentry.io/platforms/python/guides/falcon/

    """
    if not sentry_dsn:
        LOGGER.warning("no sentry_dsn set")
        return

    release = get_release(basedir)

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FalconIntegration()],
        send_default_pii=False,
        release=release,
        server_name=host_id,
    )
    LOGGER.info("set up sentry falcon integration")


def setup_sentry_logging(basedir, host_id, sentry_dsn):
    """Set up Sentry for using logging integration"""
    if not sentry_dsn:
        LOGGER.warning("no sentry_dsn set")
        return

    release = get_release(basedir)

    sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[sentry_logging],
        send_default_pii=False,
        release=release,
        server_name=host_id,
    )
    LOGGER.info("set up sentry logging integration")
