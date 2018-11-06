# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import time
from io import BytesIO
from gzip import GzipFile
from functools import wraps

import logging
import requests
import markus
from botocore.exceptions import ClientError
from google.cloud.storage.client import Bucket as google_Bucket
from cache_memoize import cache_memoize

from django.conf import settings

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

        for line in lines:
            yield line

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
    if isinstance(source, google_Bucket):
        blob = source.get_blob(key)
        if blob:
            return blob.public_url
        return False
    else:
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
    return requests.head(url).status_code == 200


class SymbolDownloader:
    """
    Class for the following S3 tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.
    3. Give me a stream for this particular symbol.

    This class takes a list of URLs. If the URL contains ``access=public``
    in the query string part, this class will use ``requests.get`` or
    ``requests.head`` depending on the task.
    If the URL does NOT contain ``access=public`` it will use a
    ``boto3`` S3 client to do the check or download.

    So, with the 3 tasks listed above, there are 6 different things
    this class can do.

    When you use ``self.get_symbol_stream()`` it will return a generator
    whose field value is always a URL or a tuple. The tuple is going to be
    ``('name-of-the-bucket', 'full-path-to-the-object-key')``. This
    is useful when you need to parse the stream and get extra information
    about where the symbol stream came from. For example::

        >>> d = SymbolDownloader(['https://s3-us-we...1/?access=public'])
        >>> stream = d.get_symbol_stream(
        ...    'nss3.pdb', '9354378E7F4E4322A83EA57C483671962', 'nss3.sym')
        >>> next(stream)
        'https://s3-us-we...s3.pdb/9354378E7F4E4322A83EA57C483671962/nss3.sym'
        >>> for line in stream:
        ...    line
        ...    break
        ...
        'MODULE windows x86 9354378E7F4E4322A83EA57C483671962 nss3.pdb'

    Or, if using a non-public URL::

        >>> # Same as above but without '?access=public' ending
        >>> d = SymbolDownloader(['https://s3-us-we...1/'])
        >>> stream = d.get_symbol_stream(
        ...    'nss3.pdb', '9354378E7F4E4322A83EA57C483671962', 'nss3.sym')
        >>> pprint(next(stream))
        ('org.mozilla.crash-stats.symbols-public',
         'v1/nss3.pdb/9354378E7F4E4322A83EA57C483671962/nss3.sym')
        >>> for line in stream:
        ...    line
        ...    break
        ...
        'MODULE windows x86 9354378E7F4E4322A83EA57C483671962 nss3.pdb'
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
                if source.is_google_cloud_storage:
                    bucket = source.get_or_load_bucket()
                    exists_in_source.invalidate(
                        bucket, self._make_key(prefix, symbol, debugid, filename)
                    )
                else:
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
                # If it's a private bucket we use boto3 or google cloud storage.
                key = self._make_key(prefix, symbol, debugid, filename)
                logger.debug(f"Looking for symbol file {key!r} in bucket {source.name}")

                if source.is_google_cloud_storage:
                    bucket = source.get_or_load_bucket()
                    url = exists_in_source(bucket, key, _refresh=refresh_cache)
                    if not url:
                        continue
                    return {"url": url}

                else:
                    if not exists_in_source(source, key, _refresh=refresh_cache):
                        continue

                    # It exists if we're still here.
                    return {"bucket_name": source.name, "key": key, "source": source}

            elif source.is_google_cloud_storage:
                raise NotImplementedError(
                    "Currently don't support regular HTTP download from GCS."
                )

            else:
                # We'll put together the URL manually
                file_url = "{}/{}".format(
                    source.base_url, self._make_key(prefix, symbol, debugid, filename)
                )
                logger.debug(f"Looking for symbol file by URL {file_url!r}")
                if check_url_head(file_url, _refresh=refresh_cache):
                    return {"url": file_url, "source": source}

    def _get_stream(self, symbol, debugid, filename):
        for source in self.sources:

            prefix = source.prefix
            assert prefix

            if source.private:
                # If it's a private bucket we use boto3 or google cloud storage.

                key = "{}/{}/{}/{}".format(
                    prefix,
                    symbol,
                    # The are some legacy use case where the debug ID might
                    # not already be uppercased. If so, we override it.
                    # Every debug ID is always in uppercase.
                    debugid.upper(),
                    filename,
                )
                logger.debug(f"Looking for symbol file {key!r} in bucket {source.name}")

                if source.is_google_cloud_storage:
                    bucket = source.get_or_load_bucket()
                    with metrics.timer("symboldownloader_get_blob"):
                        blob = bucket.get_blob(key)
                    if blob is None:
                        continue

                    yield (source.name, key)
                    bytestream = BytesIO()
                    blob.download_to_file(bytestream)
                    bytestream.seek(0)
                    whole = bytestream.read().decode("utf-8")
                    for line in whole.splitlines():
                        if line:
                            yield line
                    return
                else:
                    try:
                        with metrics.timer("symboldownloader_get_object"):
                            response = source.client.get_object(
                                Bucket=source.name, Key=key
                            )
                        stream = response["Body"]
                        # But if the content encoding is gzip we have
                        # re-wrap the stream.
                        if response.get("ContentEncoding") == "gzip":
                            with metrics.timer("symboldownloader_get_object_read"):
                                body = response["Body"].read()
                            metrics.incr(
                                "symboldownloader_download_bytes",
                                len(body),
                                tags=["encoding:gzip"],
                            )
                            bytestream = BytesIO(body)
                            stream = GzipFile(None, "rb", fileobj=bytestream)
                        yield (source.name, key)
                        try:
                            for line in iter_lines(stream):
                                yield line.decode("utf-8")
                            return
                        except OSError as exception:
                            if "Not a gzipped file" in str(exception):
                                logger.warning(
                                    "OSError ({!r}) when downloading {}/{}"
                                    "".format(str(exception), source.name, key)
                                )
                                continue
                            # Who knows what other OSErrors might happen when
                            # it's not a problem of being a gzip content?!
                            raise  # pragma: no cover

                    except ClientError as exception:
                        if exception.response["Error"]["Code"] == "NoSuchKey":
                            # basically, a convuluted way of saying 404
                            continue
                        # Any other errors we're not yet aware of, proceeed
                        raise

            elif source.is_google_cloud_storage:
                raise NotImplementedError(
                    "Currently don't support regular HTTP download from GCS."
                )

            else:
                # If it's not a private bucket, we can use requests
                # to download via HTTP.

                # We'll put together the URL manually
                file_url = "{}/{}/{}/{}/{}".format(
                    source.base_url, prefix, symbol, debugid.upper(), filename
                )
                logger.debug(f"Looking for symbol file by URL {file_url!r}")
                response = requests.get(file_url, stream=True)
                if response.status_code == 404:
                    # logger.warning('{} 404 Not Found'.format(file_url))
                    continue
                elif response.status_code == 200:
                    # Files downloaded from S3 should be UTF-8 but it's
                    # unlikely that S3 exposes this in a header.
                    # If the Content-Type in 'text/plain' requests will
                    # assume the ISO-8859-1 encoding (this is according
                    # to RFC 2616).
                    # But if the content type is 'binary/octet-stream' it
                    # can't assume any encoding so it will be returned
                    # as a bytestring.
                    if not response.encoding:
                        response.encoding = "utf-8"
                    yield file_url
                    try:
                        for line in response.iter_lines():
                            # filter out keep-alive newlines
                            if line:
                                line = line.decode("utf-8")
                                yield line
                        # Stop the iterator
                        return
                    except requests.exceptions.ContentDecodingError as exc:
                        logger.warning(f"{exc!r} when downloading {source}")
                        continue
                else:
                    logger.warning(
                        "{} {} ({})".format(
                            source, response.status_code, response.content
                        )
                    )
                    raise SymbolDownloadError(response.status_code, str(source))

        # All URLs exhausted
        raise SymbolNotFound(symbol, debugid, filename)

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

    def get_symbol_stream(self, symbol, debugid, filename):
        """return a body stream for download if the file can be found.
        The object is a regular Python generator.
        The first item in the generator is always the URL or the
        (bucketname, objectkey) tuple if found."""
        return self._get_stream(symbol, debugid, filename)
