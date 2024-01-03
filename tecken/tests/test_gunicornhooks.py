# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from tecken import gunicornhooks


def test_worker_abort_emits_metric(metricsmock):
    # NOTE(willkg): we pass in a None here, but it's really expecting a gunicorn worker
    # instance. Since our worker_abort hook doesn't do anything with the worker
    # instance, that's fine.
    gunicornhooks.worker_abort(None)

    metricsmock.assert_incr(
        "tecken.gunicorn_worker_abort", value=1, tags=["host:testnode"]
    )
