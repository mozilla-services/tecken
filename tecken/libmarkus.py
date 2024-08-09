# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from pathlib import Path

import markus
from markus.filters import AddTagFilter, RegisteredMetricsFilter
import yaml


_IS_MARKUS_SETUP = False

METRICS = markus.get_metrics("tecken")


# Complete index of all metrics. This is used in documentation and to filter outgoing
# metrics.
def _load_registered_metrics():
    # Load the metrics yaml file in this directory
    path = Path(__file__).parent / "statsd_metrics.yaml"
    with open(path) as fp:
        data = yaml.safe_load(fp)
    return data


STATSD_METRICS = _load_registered_metrics()


def set_up_markus(backends, hostname, debug=False):
    global _IS_MARKUS_SETUP, METRICS
    if _IS_MARKUS_SETUP:
        return

    markus.configure(backends)

    if debug:
        # In local dev and test environments, we want the RegisteredMetricsFilter to
        # raise exceptions when metrics are used incorrectly.
        metrics_filter = RegisteredMetricsFilter(
            registered_metrics=STATSD_METRICS, raise_error=True
        )
        METRICS.filters.append(metrics_filter)

    if hostname:
        # Define host tag here instead of in the backend so it shows up in tests
        METRICS.filters.append(AddTagFilter(f"host:{hostname}"))

    _IS_MARKUS_SETUP = True
