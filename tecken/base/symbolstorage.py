# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from email.utils import parsedate_to_datetime
from functools import wraps
import time
from typing import Optional
from urllib.parse import quote

import logging

from django.conf import settings

from tecken.libmarkus import METRICS
from tecken.librequests import session_with_retries
from tecken.storage import StorageBucket


logger = logging.getLogger("tecken")


def set_time_took(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        t0 = time.time()
        result = method(self, *args, **kwargs)
        t1 = time.time()
        self.time_took = t1 - t0
        return result

    return wrapper


@METRICS.timer_decorator("symboldownloader_exists")
def get_last_modified(url: str) -> Optional[int]:
    """
    Get the last modified date of the given URL.

    This function performs a HEAD request to the given URL. If the status code is 200,
    the Last-Modified header is parsed into a Unix timestamp and returned.
    If the response does not include a Last-Modified header, or the header can't be
    parsed, the current time is returned. If the response status code is not 200, the
    function returns None.

    :arg url: The target URL.
    :returns: The timestamp of the last modification of the resource at the URL or `None`.
    """
    session = session_with_retries(status_forcelist=(429, 500, 503))
    resp = session.head(url)
    # NOTE(willkg): we get a 403 from S3 buckets HTTP requests, so we want to ignore
    # those
    if resp.status_code not in (200, 403, 404):
        logger.error(f"get_last_modified: {url} status code is {resp.status_code}")
    if resp.status_code == 200:
        try:
            last_modified = parsedate_to_datetime(resp.headers["last-modified"])
            return int(last_modified.timestamp())
        except (ValueError, KeyError):
            # KeyError occurs when the response does not hav a Last-Modified header,
            # and ValueError occurs if the Last-Modified header isn't properly
            # RFC-5322-formatted. Neither of this should ever happen, since S3 always
            # includes a properly formatted Last-Modified header in responses, so
            # this code is just a fallback to avoid erroring out if something
            # unexpected happened.
            logger.error(
                "get_last_modified: HEAD request to %s did not return "
                "a valid last-modified header",
                url,
            )
            return int(time.time())


class SymbolStorage:
    """
    Class for the following S3 tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.

    This class takes a list of URLs.

    """

    def __init__(
        self, urls, file_prefix=settings.SYMBOL_FILE_PREFIX, try_url_index=None
    ):
        self.urls = urls
        self._sources = None
        self.file_prefix = file_prefix
        self.try_url_index = try_url_index

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

    def _get(self, symbol, debugid, filename):
        """Return a dict if the symbol can be found.

        Dict includes a "url" key.

        Consumers of this method can use the fact that anything truish
        was returned as an indication that the symbol actually exists.

        """
        for i, source in enumerate(self.sources):
            prefix = source.prefix
            assert prefix

            # We'll put together the URL manually
            file_url = "{}/{}".format(
                source.base_url, self.make_url_path(prefix, symbol, debugid, filename)
            )
            logger.debug(f"Looking for symbol file by URL {file_url!r}")
            if last_modified := get_last_modified(file_url):
                age_days = int(time.time() - last_modified) // 86_400  # seconds per day
                if i == self.try_url_index:
                    tags = ["storage:try"]
                else:
                    tags = ["storage:regular"]
                METRICS.histogram("symboldownloader.file_age_days", age_days, tags)
                return {
                    "url": file_url,
                    "source": source,
                }

    @set_time_took
    def has_symbol(self, symbol, debugid, filename):
        """return True if the symbol can be found, False if not
        found in any of the URLs provided."""
        return bool(self._get(symbol, debugid, filename))

    @set_time_took
    def get_symbol_url(self, symbol, debugid, filename):
        """Return the redirect URL or None.

        If we return None it means we can't find the object in any of the URLs provided.

        """
        found = self._get(symbol, debugid, filename)
        if found:
            return found["url"]


normal_storage = SymbolStorage(
    settings.SYMBOL_URLS, file_prefix=settings.SYMBOL_FILE_PREFIX
)
try_storage = SymbolStorage(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
    try_url_index=len(settings.SYMBOL_URLS),
)
