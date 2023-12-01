# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Gunicorn server hooks.

See https://docs.gunicorn.org/en/stable/settings.html#server-hooks

Note: Don't import anything that involves Django machinery here.
"""

import markus


metrics = markus.get_metrics("tecken")


def worker_abort(worker):
    """Emit metric when a Gunicorn worker is terminated from timeout

    .. Note::

       This gets called by the Gunicorn worker handle_abort() function so it'll use the
       markus and logging configuration of the Django webapp.

    """
    metrics.incr("gunicorn_worker_abort")
