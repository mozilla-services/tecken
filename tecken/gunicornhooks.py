# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Gunicorn server hooks.

See https://docs.gunicorn.org/en/stable/settings.html#server-hooks
"""

import markus

from tecken import settings


metrics = markus.get_metrics("tecken")


def configure_markus():
    markus.configure(settings.MARKUS_BACKENDS)


def worker_abort(worker):
    metrics.incr("gunicorn_worker_abort")
