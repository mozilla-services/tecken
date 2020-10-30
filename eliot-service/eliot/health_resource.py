# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Application-health related Falcon resources.
"""

import json

from dockerflow.version import get_version
import falcon
import markus


METRICS = markus.get_metrics(__name__)


class BrokenResource:
    """Handle ``/__broken__`` endpoint."""

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        METRICS.incr("broken.count")
        # This is intentional breakage
        raise Exception("intentional exception")


class VersionResource:
    """Handle ``/__version__`` endpoint."""

    def __init__(self, basedir):
        self.basedir = basedir

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        METRICS.incr("version.count")
        version_info = json.dumps(get_version(self.basedir) or {})
        resp.content_type = "application/json; charset=utf-8"
        resp.status = falcon.HTTP_200
        resp.body = version_info


class LBHeartbeatResource:
    """Handle ``/__lbheartbeat__`` to let the load balancing know application health."""

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        METRICS.incr("lbheartbeat.count")
        resp.content_type = "application/json; charset=utf-8"
        resp.status = falcon.HTTP_200


class HeartbeatResource:
    """Handle ``/__heartbeat__`` for app health."""

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        METRICS.incr("heartbeat.count")
        resp.content_type = "application/json; charset=utf-8"
        resp.status = falcon.HTTP_200
