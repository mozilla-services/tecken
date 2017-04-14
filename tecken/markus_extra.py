from django.core.cache import cache
from django.conf import settings

from markus.backends import BackendBase


class CacheMetrics(BackendBase):
    """This is a markus backend that is useful in local development.
    It uses the cache framework to store increments on cache hits and misses.
    """

    def __init__(self, options):
        self._log_time = options.get('log_time', 60 * 60)
        if not settings.DEBUG:
            import warnings
            warnings.warn(
                "This metrics backend should not be used in production "
                "since in production we should be using Statsd."
            )

    def incr(self, stat, value, tags=None):
        try:
            cache.incr(stat, value)
        except ValueError:
            # First time incrementing this key
            cache.set(stat, value, self._log_time)

    gauge = incr

    def timing(self, stat, value, tags=None):
        pass

    def histogram(self, stat, value, tags=None):
        pass
