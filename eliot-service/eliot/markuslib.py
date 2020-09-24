# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import markus


_IS_MARKUS_SETUP = False


def setup_metrics(app_config, logger=None):
    """Initialize and configures the metrics system."""
    global _IS_MARKUS_SETUP
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
    _IS_MARKUS_SETUP = True
