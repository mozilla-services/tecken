# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import time
from functools import partialmethod

import markus
from markus import INCR, GAUGE, HISTOGRAM, TIMING
from markus.backends import BackendBase
from markus.filters import AddTagFilter

_IS_MARKUS_SETUP = False
METRICS = markus.get_metrics("tecken")


def setup_markus(backends, hostname):
    global _IS_MARKUS_SETUP, METRICS
    if _IS_MARKUS_SETUP:
        return

    markus.configure(backends)

    if hostname:
        # Define host tag here instead of in the backend so it shows up in tests
        METRICS.filters.append(AddTagFilter(f"host:{hostname}"))

    _IS_MARKUS_SETUP = True


class LogAllMetricsKeys(BackendBase):  # pragma: no cover
    """A markus backend that uses the filesystem to jot down ALL keys
    that ever get used.
    This then becomes handy when you want to make sure that you're using
    all metrics in places like Datadog.
    If you're not, it's maybe time to delete the metrics key.

    Don't enable this in production. Use it during local development
    and/or local test running.
    """

    def notice_use(self, state, type, *args, **kwargs):
        filename = "all-metrics-keys.json"
        try:
            with open(filename) as f:
                all_keys = json.load(f)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            # This file gets written in an not thread-safe way
            # so sometimes the file is all messed up. Pretend
            # it didn't exist if the exception was a JSONDecodeError.
            all_keys = {
                "_documentation": (
                    "This file was created so you can see all metrics "
                    "keys that get used. It won't delete keys that are no "
                    "longer used. Feel free to delete this file and run again."
                )
            }
        all_keys[state] = {
            "type": type,
            "timestamp": time.time(),
            "count": all_keys.get(state, {}).get("count", 0) + 1,
        }
        with open(filename, "w") as f:
            json.dump(all_keys, f, sort_keys=True, indent=3)

    incr = partialmethod(notice_use, type=INCR)
    gauge = partialmethod(notice_use, type=GAUGE)
    histogram = partialmethod(notice_use, type=HISTOGRAM)
    timing = partialmethod(notice_use, type=TIMING)
