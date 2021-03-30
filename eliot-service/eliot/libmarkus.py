# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Utilities for setting up markus.
"""

from dataclasses import dataclass
import logging

import markus
from markus.main import MetricsFilter


_IS_MARKUS_SETUP = False

LOGGER = logging.getLogger(__name__)


@dataclass
class Metric:
    stat_type: str
    description: str


# Complete index of all Eliot metrics. This is used in documentation and to filter
# outgoing metrics.
ELIOT_METRICS = {
    "eliot.symbolicate.api": Metric(
        stat_type="timing",
        description="""\
        Timer for long a symbolication API request takes to handle.

        Tags:

        * ``version``: the symbolication api version

          * ``v4``: the v4 API
          * ``v5``: the v5 API
        """,
    ),
    "eliot.symbolicate.request_error": Metric(
        stat_type="incr",
        description="""\
        Counter for errors in incoming symbolication requests.

        Tags:

        * ``reason``: the error reason

          * ``bad_json``: the payload is not valid JSON
          * ``invalid_modules``: the payload has invalid modules
          * ``invalid_stacks``: the payload has invalid stacks
          * ``too_many_jobs``: (v5) the payload has too many jobs in it
        """,
    ),
    "eliot.downloader.download": Metric(
        stat_type="histogram",
        description="""\
        Timer for how long it takes to download SYM files.

        Tags:

        * ``response``: the HTTP response we got back

          * ``success``: HTTP 200
          * ``fail``: HTTP 404, 500, etc
        """,
    ),
    "eliot.symbolicate.parse_sym_file.error": Metric(
        stat_type="incr",
        description="""\
        Counter for when a sym file fails to parse.

        Tags:

        * ``reason``: the reason it failed to parse

          * ``bad_debug_id``: debug_id is not valid
          * ``sym_debug_id_lookup_error``: when the debug_id isn't in the sym file
          * ``sym_tmp_file_error``: error creating tmp file to save the sym file
            to disk
        """,
    ),
    "eliot.symbolicate.parse_sym_file.parse": Metric(
        stat_type="timing",
        description="""\
        Timer for how long it takes to parse sym files with Symbolic.
        """,
    ),
    "eliot.symbolicate.jobs_count": Metric(
        stat_type="histogram",
        description="""\
        Histogram for how many jobs were in the symbolication request.

        Tags:

        * ``version``: the symbolication api version

          * ``v4``: the v4 API
          * ``v5``: the v5 API
        """,
    ),
    "eliot.symbolicate.stacks_count": Metric(
        stat_type="histogram",
        description="""\
        Histogram for how many stacks per job were in the symbolication request.

        Tags:

        * ``version``: the symbolication api version

          * ``v4``: the v4 API
          * ``v5``: the v5 API
        """,
    ),
    "eliot.symbolicate.frames_count": Metric(
        stat_type="histogram",
        description="""\
        Histogram for how many frames per stack were in the symbolication request.
        """,
    ),
    "eliot.diskcache.get": Metric(
        stat_type="histogram",
        description="""\
        Timer for how long it takes to get symcache files from the disk cache.

        Tags:

        * ``result``: the cache result

          * ``hit``: the file was in cache
          * ``error``: the file was in cache, but there was an error reading it
          * ``miss``: the file was not in cache
        """,
    ),
    "eliot.diskcache.set": Metric(
        stat_type="histogram",
        description="""\
        Timer for how long it takes to save a symcache file to the disk cache.

        Tags:

        * ``result``: the cache result

          * ``success``: the file was saved successfully
          * ``fail``: the file was not saved successfully
        """,
    ),
    "eliot.diskcache.evict": Metric(
        stat_type="incr",
        description="Counter for disk cache evictions.",
    ),
    "eliot.diskcache.usage": Metric(
        stat_type="gauge", description="Gauge for how much of the cache is in use."
    ),
}


def setup_metrics(app_config, logger=None):
    """Initialize and configures the metrics system."""
    global _IS_MARKUS_SETUP, METRICS
    if _IS_MARKUS_SETUP:
        return

    markus_backends = [
        {
            "class": "markus.backends.datadog.DatadogMetrics",
            "options": {
                "statsd_host": app_config("statsd_host"),
                "statsd_port": app_config("statsd_port"),
                "statsd_namespace": app_config("statsd_namespace"),
            },
        }
    ]
    if app_config("local_dev_env"):
        markus_backends.append(
            {
                "class": "markus.backends.logging.LoggingMetrics",
                "options": {
                    "logger_name": "markus",
                    "leader": "METRICS",
                },
            }
        )
    markus.configure(markus_backends)

    if app_config("local_dev_env"):
        # In local dev environment, we want the RegisteredMetricsFilter to
        # raise exceptions when metrics are used incorrectly.
        metrics_filter = RegisteredMetricsFilter(metrics=ELIOT_METRICS)
        METRICS.filters.append(metrics_filter)

    _IS_MARKUS_SETUP = True


class UnknownMetric(Exception):
    pass


class MetricHasWrongType(Exception):
    pass


class RegisteredMetricsFilter(MetricsFilter):
    """Filter for enforcing registered metrics emission.

    This is only used in local development and tests.

    """

    def __init__(self, metrics):
        self.metrics = metrics

    def filter(self, record):
        metric = self.metrics.get(record.key)

        if metric is None:
            raise UnknownMetric("metrics key %r is unknown" % record.key)

        elif record.stat_type != metric.stat_type:
            raise MetricHasWrongType(
                "metrics key %r has wrong type; got %s expecting %s"
                % (
                    record.key,
                    record.stat_type,
                    metric.stat_type,
                )
            )

        return record


METRICS = markus.get_metrics()
