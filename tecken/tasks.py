import time

from django.core.cache import cache

from .celery import celery


@celery.task
def sample_task(key, value, expires=10):
    """Really basic task that simply puts a key and value in the
    regular cache. This way, it can be used to test if celery is working.

    This is never expected to be used for anything run-time in production.
    Just for basic systemtests.
    """
    time.sleep(0.1)  # artificial just so that there's a tiny delay
    cache.set(key, value, expires)
