# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from collections import OrderedDict
import json
import logging

from dockerflow.version import get_version
import falcon
import markus


logger = logging.getLogger(__name__)
mymetrics = markus.get_metrics("health")


class BrokenResource:
    """Handle ``/__broken__`` endpoint."""

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        mymetrics.incr("broken.count")
        # This is intentional breakage
        raise Exception("intentional exception")


class VersionResource:
    """Handle ``/__version__`` endpoint."""

    def __init__(self, basedir):
        self.basedir = basedir

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        mymetrics.incr("version.count")
        version_info = json.dumps(get_version(self.basedir) or {})
        resp.content_type = "application/json; charset=utf-8"
        resp.status = falcon.HTTP_200
        resp.body = version_info


class LBHeartbeatResource:
    """Handle ``/__lbheartbeat__`` to let the load balancing know application health."""

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        mymetrics.incr("lbheartbeat.count")
        resp.content_type = "application/json; charset=utf-8"
        resp.status = falcon.HTTP_200


class HealthState:
    """Object representing health of system."""

    def __init__(self):
        self.errors = []
        self.statsd = {}

    def add_statsd(self, name, key, value):
        """Add a key -> value gauge."""
        if not isinstance(name, str):
            name = name.__class__.__name__
        self.statsd["%s.%s" % (name, key)] = value

    def add_error(self, name, msg):
        """Add an error."""
        # Use an OrderedDict here so we can maintain key order when converting
        # to JSON.
        d = OrderedDict([("name", name), ("msg", msg)])
        self.errors.append(d)

    def is_healthy(self):
        """Return whether this represents a healthy state."""
        return len(self.errors) == 0

    def to_dict(self):
        """Convert state to a dict."""
        return OrderedDict([("errors", self.errors), ("info", self.statsd)])


class HeartbeatResource:
    """Handle ``/__heartbeat__`` for app health."""

    def __init__(self, app):
        self.app = app

    def on_get(self, req, resp):
        """Implement GET HTTP request."""
        mymetrics.incr("heartbeat.count")
        state = HealthState()

        # So we're going to think of Eliot like a big object graph and traverse
        # passing along the HealthState instance. Then, after traversing the object
        # graph, we'll tally everything up and deliver the news.
        for resource in self.app.get_resources():
            if hasattr(resource, "check_health"):
                resource.check_health(state)

        # Go through and call gauge for each statsd item.
        for k, v in state.statsd.items():
            mymetrics.gauge(k, value=v)

        if state.is_healthy():
            resp.status = falcon.HTTP_200
        else:
            resp.status = falcon.HTTP_503
        resp.body = json.dumps(state.to_dict())
