# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.core.cache import cache

from celery import shared_task


class SampleTaskError(Exception):
    """when something isn't right inside the sample_task."""


@shared_task
def sample_task(key, value, expires=10):
    """Really basic task that simply puts a key and value in the
    regular cache. This way, it can be used to test if celery is working.

    This is never expected to be used for anything run-time in production.
    Just for basic systemtests.
    """
    if not value:
        raise SampleTaskError(f"'value' is falsy {value!r}")
    cache.set(key, value, expires)
