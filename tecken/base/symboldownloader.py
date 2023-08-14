# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from functools import wraps
import time
from urllib.parse import quote

from cache_memoize import cache_memoize
import logging
import markus

from django.conf import settings

from tecken.librequests import session_with_retries
from tecken.storage import StorageBucket


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


class SymbolNotFound(Exception):
    """Happens when you try to download a symbols file that doesn't exist"""


class SymbolDownloadError(Exception):
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url


def set_time_took(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        t0 = time.time()
        result = method(self, *args, **kwargs)
        t1 = time.time()
        self.time_took = t1 - t0
        return result

    return wrapper


@cache_memoize(
    settings.SYMBOLDOWNLOAD_EXISTS_TTL_SECONDS,
    hit_callable=lambda *a, **k: metrics.incr("symboldownloader_exists_cache_hit", 1),
    miss_callable=lambda *a, **k: metrics.incr("symboldownloader_exists_cache_miss", 1),
)
@metrics.timer_decorator("symboldownloader_exists")
def check_url_head(url):
    session = session_with_retries()
    resp = session.head(url)
    # NOTE(willkg): we get a 403 from S3 buckets HTTP requests, so we want to ignore
    # those
    if resp.status_code not in (200, 403, 404):
        logger.error(f"check_url_head: {url} status code is {resp.status_code}")
    return resp.status_code == 200


class SymbolDownloader:
    """
    Class for the following S3 tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.

    This class takes a list of URLs.

    """

    def __init__(self, urls, file_prefix=settings.SYMBOL_FILE_PREFIX):
        self.urls = urls
        self._sources = None
        self.file_prefix = file_prefix

    def __repr__(self):
        return f"<{self.__class__.__name__} urls={self.urls}>"

    def _get_sources(self):
        for url in self.urls:
            # The URL is expected to have the bucket name as the first
            # part of the pathname.
            # In the future we might expand to a more elaborate scheme.
            yield StorageBucket(url, file_prefix=self.file_prefix)

    @property
    def sources(self):
        if self._sources is None:
            self._sources = list(self._get_sources())
        return self._sources

    def invalidate_cache(self, symbol, debugid, filename):
        # Because we can't know exactly which source (aka URL) was
        # used when the key was cached by exists_in_source() we have
        # to iterate over the source.
        for source in self.sources:
            prefix = source.prefix
            assert prefix
            file_url = "{}/{}".format(
                source.base_url, self.make_url_path(prefix, symbol, debugid, filename)
            )
            check_url_head.invalidate(file_url)

    @staticmethod
    def make_url_path(prefix, symbol, debugid, filename):
        """Generates a url quoted path which works with HTTP requests against AWS S3
        buckets

        :arg prefix:
        :arg symbol:
        :arg debugid:
        :arg filename:

        :returns: url quoted relative path to be joined with a base url

        """
        # The are some legacy use case where the debug ID might not already be
        # uppercased. If so, we override it. Every debug ID is always in uppercase.
        return quote(f"{prefix}/{symbol}/{debugid.upper()}/{filename}")

    def _get(self, symbol, debugid, filename, refresh_cache=False):
        """Return a dict if the symbol can be found.

        Dict includes a "url" key.

        Consumers of this method can use the fact that anything truish
        was returned as an indication that the symbol actually exists.

        """
        for source in self.sources:
            prefix = source.prefix
            assert prefix

            # We'll put together the URL manually
            file_url = "{}/{}".format(
                source.base_url, self.make_url_path(prefix, symbol, debugid, filename)
            )
            logger.debug(f"Looking for symbol file by URL {file_url!r}")
            if check_url_head(file_url, _refresh=refresh_cache):
                return {"url": file_url, "source": source}

    @set_time_took
    def has_symbol(self, symbol, debugid, filename, refresh_cache=False):
        """return True if the symbol can be found, False if not
        found in any of the URLs provided."""
        return bool(self._get(symbol, debugid, filename, refresh_cache=refresh_cache))

    @set_time_took
    def get_symbol_url(self, symbol, debugid, filename, refresh_cache=False):
        """Return the redirect URL or None.

        If we return None it means we can't find the object in any of the URLs provided.

        """
        found = self._get(symbol, debugid, filename, refresh_cache=refresh_cache)
        if found:
            return found["url"]
