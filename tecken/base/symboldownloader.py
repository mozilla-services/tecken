# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import time
from functools import wraps

from cache_memoize import cache_memoize
import logging
import markus

from django.conf import settings

from tecken.librequests import session_with_retries
from tecken.storage import StorageBucket


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")

ITER_CHUNK_SIZE = 512


class SymbolNotFound(Exception):
    """Happens when you try to download a symbols file that doesn't exist"""


class SymbolDownloadError(Exception):
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url


def iter_lines(stream, chunk_size=ITER_CHUNK_SIZE):
    """Iterates over the response data, one line at a time.  When
    stream=True is set on the request, this avoids reading the
    content at once into memory for large responses.

    .. note:: This method is not reentrant safe.
    """

    pending = None

    for chunk in iter(lambda: stream.read(chunk_size), b""):
        if pending is not None:
            chunk = pending + chunk

        lines = chunk.splitlines()

        if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
            pending = lines.pop()
        else:
            pending = None

        yield from lines

    if pending is not None:
        yield pending


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
    args_rewrite=lambda source, key: (source.name, key),
    hit_callable=lambda *a, **k: metrics.incr("symboldownloader_exists_cache_hit", 1),
    miss_callable=lambda *a, **k: metrics.incr("symboldownloader_exists_cache_miss", 1),
)
@metrics.timer_decorator("symboldownloader_exists")
def exists_in_source(source, key):
    """Return a key or URL or something truthy if it exists. False otherwise.

    The reason for returning False, when it's not there in the remote storage,
    is because if you use `None` it can't be cached since the memoizer function
    considers `None` as a "cache failure" and not a real value."""
    response = source.client.list_objects_v2(Bucket=source.name, Prefix=key)
    for obj in response.get("Contents", []):
        if obj["Key"] == key:
            # It exists!
            return key
    return False


@cache_memoize(
    settings.SYMBOLDOWNLOAD_EXISTS_TTL_SECONDS,
    hit_callable=lambda *a, **k: metrics.incr(
        "symboldownloader_public_exists_cache_hit", 1
    ),
    miss_callable=lambda *a, **k: metrics.incr(
        "symboldownloader_public_exists_cache_miss", 1
    ),
)
@metrics.timer_decorator("symboldownloader_public_exists")
def check_url_head(url):
    session = session_with_retries()
    resp = session.head(url)
    if resp.status_code not in (200, 404):
        logger.error(f"check_url_head: {url} status code is {resp.status_code}")
    return resp.status_code == 200


class SymbolDownloader:
    """
    Class for the following S3 tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.

    This class takes a list of URLs. If the URL contains ``access=public``
    in the query string part, this class will use ``requests.get`` or
    ``requests.head`` depending on the task.
    If the URL does NOT contain ``access=public`` it will use a
    ``boto3`` S3 client to do the check or download.

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
            if source.private:
                # At some point we ran
                # exists_in_source(source, key)
                # But that function is wrapped and now has an extra
                # function to "undoing" it.
                exists_in_source.invalidate(
                    source, self._make_key(prefix, symbol, debugid, filename)
                )
            else:
                file_url = "{}/{}".format(
                    source.base_url, self._make_key(prefix, symbol, debugid, filename)
                )
                check_url_head.invalidate(file_url)

    @staticmethod
    def _make_key(prefix, symbol, debugid, filename):
        return "{}/{}/{}/{}".format(
            prefix,
            symbol,
            # The are some legacy use case where the debug ID might
            # not already be uppercased. If so, we override it.
            # Every debug ID is always in uppercase.
            debugid.upper(),
            filename,
        )

    def _get(self, symbol, debugid, filename, refresh_cache=False):
        """Return a dict if the symbol can be found. The dict will
        either be `{'url': ...}` or `{'buckey_name': ..., 'key': ...}`
        depending on if the symbol was found a public bucket or a
        private bucket.
        Consumers of this method can use the fact that anything truish
        was returned as an indication that the symbol actually exists."""
        for source in self.sources:
            prefix = source.prefix
            assert prefix

            if source.private:
                # If it's a private bucket we use boto3
                key = self._make_key(prefix, symbol, debugid, filename)
                logger.debug(f"Looking for symbol file {key!r} in bucket {source.name}")

                if not exists_in_source(source, key, _refresh=refresh_cache):
                    continue

                # It exists if we're still here.
                return {"bucket_name": source.name, "key": key, "source": source}

            else:
                # We'll put together the URL manually
                file_url = "{}/{}".format(
                    source.base_url, self._make_key(prefix, symbol, debugid, filename)
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
        """return the redirect URL or None. If we return None
        it means we can't find the object in any of the URLs provided."""
        found = self._get(symbol, debugid, filename, refresh_cache=refresh_cache)
        if found:
            if "url" in found:
                return found["url"]

            # If a URL wasn't returned, the bucket it was found in
            # was not public.
            bucket_name = found["bucket_name"]
            key = found["key"]
            # generate_presigned_url() actually works for both private
            # and public buckets.
            return found["source"].client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": key},
                # Left commented-in to remind us of what the default is
                # ExpiresIn=3600
            )
