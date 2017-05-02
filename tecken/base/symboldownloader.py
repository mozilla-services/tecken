from io import BytesIO
from gzip import GzipFile

import logging
from urllib.parse import urlparse

import requests
import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger('tecken')

ITER_CHUNK_SIZE = 512


class SymbolNotFound(Exception):  # XXX is this ever used?!
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

    for chunk in iter(lambda: stream.read(chunk_size), b''):

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


class _SymbolSource:
    """Deconstruct a URL that points to a symbol source.
    The URL is expected to be like a URL but there are things we can
    immediately infer from it. For example, if the source is public
    we expect 'access=public' in the query string part.

    Usage::

        >>> s = _SymbolSource(
        ...    'https://s3-us-west-2.amazonaws.com/bucket/prefix?access=public'
        )
        >>> s.netloc
        's3-us-west-2.amazonaws.com'
        >>> s.bucket_name
        'bucket'
        >>> s.private  # note, private is usually default
        False
        >>> s.prefix
        'prefix'

    """
    def __init__(self, url):
        parsed = urlparse(url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
        self.private = 'access=public' not in parsed.query
        try:
            bucket_name, prefix = parsed.path[1:].split('/', 1)
        except ValueError:
            prefix = ''
            bucket_name = parsed.path[1:]
        self.bucket_name = bucket_name
        self.prefix = prefix

    def __str__(self):
        return '{}://{}/{}/{}'.format(
            self.scheme,
            self.netloc,
            self.bucket_name,
            self.prefix,
        )


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

    requests_operational_errors = (
        requests.exceptions.ReadTimeout,
        requests.exceptions.SSLError,
        requests.exceptions.ConnectionError,
    )

    def __init__(self, urls):
        self.urls = urls
        self.s3_client = None

    def _get_sources(self):
        """Return a generator that yields a _SymbolSource instance for
        every URL mentioned in settings.SYMBOL_URLS.
        This way, if there's a hit on the first item of settings.SYMBOL_URLS
        it will never need to parsed and dig into the second item.
        """
        for url in self.urls:
            # The URL is expected to have the bucket name as the first
            # part of the pathname.
            # In the future we might expand to a more elaborate scheme.
            yield _SymbolSource(url)

    def _get(self, symbol, debugid, filename):
        # This will automatically pick up credentials from the environment
        # variables to authenticate.

        # for private_bucket, bucket_name, prefix in self._get_sources():
        for source in self._get_sources():

            if source.private:
                if not self.s3_client:
                    self.s3_client = boto3.client('s3')

                key = '{}{}/{}/{}'.format(
                    source.prefix,
                    symbol,
                    # The are some legacy use case where the debug ID might
                    # not already be uppercased. If so, we override it.
                    # Every debug ID is always in uppercase.
                    debugid.upper(),
                    filename,
                )
                logger.debug(
                    'Looking for symbol file {!r} in bucket {!r}'.format(
                        key,
                        source.bucket_name
                    )
                )

                # By doing a head_object() lookup we will immediately know
                # if the object exists under this URL.
                # It doesn't matter yet if the client of this call is
                # doing a HEAD or a GET. We need to first know if the key
                # exists in this bucket.
                try:
                    self.s3_client.head_object(
                        Bucket=source.bucket_name,
                        Key=key,
                    )
                except ClientError as exception:
                    error_code = int(exception.response['Error']['Code'])
                    if error_code == 404:
                        continue
                    # If anything else goes wrong, it's most likely a
                    # configuration problem we should be made aware of.
                    raise

                # It exists! Yay!
                return {'bucket_name': source.bucket_name, 'key': key}

            else:
                # Return the URL if it exists
                # if not url.endswith('/'):
                #     url += '/'

                # We'll put together the URL manually
                file_url = '{}{}/{}/{}'.format(
                    source,
                    symbol,
                    debugid.upper(),
                    filename,
                )
                logger.debug(
                    'Looking for symbol file by URL {!r}'.format(
                        file_url
                    )
                )
                if requests.head(file_url).status_code == 200:
                    return {'url': file_url}

    def _get_stream(self, symbol, debugid, filename):
        # This will automatically pick up credentials from the environment
        # variables to authenticate.

        for source in self._get_sources():
            # if private_bucket:
            if source.private:

                # We're going to need the client
                if not self.s3_client:
                    self.s3_client = boto3.client('s3')

                key = '{}{}/{}/{}'.format(
                    source.prefix,
                    symbol,
                    # The are some legacy use case where the debug ID might
                    # not already be uppercased. If so, we override it.
                    # Every debug ID is always in uppercase.
                    debugid.upper(),
                    filename,
                )
                logger.debug(
                    'Looking for symbol file {!r} in bucket {!r}'.format(
                        key,
                        source.bucket_name
                    )
                )

                try:
                    response = self.s3_client.get_object(
                        Bucket=source.bucket_name,
                        Key=key,
                    )
                    stream = response['Body']
                    # But if the content encoding is gzip we have
                    # re-wrap this.
                    if response.get('ContentEncoding') == 'gzip':
                        bytestream = BytesIO(response['Body'].read())
                        stream = GzipFile(None, 'rb', fileobj=bytestream)
                    yield (source.bucket_name, key)
                    try:
                        for line in iter_lines(stream):
                            yield line.decode('utf-8')
                        return  # like a break, but for generators
                    except OSError as exception:
                        if 'Not a gzipped file' in str(exception):
                            logger.warning(
                                'OSError ({!r}) when downloading {}/{}'
                                ''.format(
                                    str(exception),
                                    source.bucket_name,
                                    key,
                                )
                            )
                            continue
                        raise

                except ClientError as exception:
                    if exception.response['Error']['Code'] == 'NoSuchKey':
                        # basically, a convuluted way of saying 404
                        continue
                    # Any other errors we're not yet aware of, proceeed
                    raise

            else:
                # Return the URL if it exists
                # if not url.endswith('/'):
                #     url += '/'

                # We'll put together the URL manually
                file_url = '{}{}/{}/{}'.format(
                    source,
                    symbol,
                    debugid.upper(),
                    filename,
                )
                logger.debug(
                    'Looking for symbol file by URL {!r}'.format(
                        file_url
                    )
                )
                try:
                    response = requests.get(file_url, stream=True)
                except self.requests_operational_errors as exception:
                    logger.warning(
                        '{!r} when downloading {}'.format(
                            exception,
                            source,
                        )
                    )
                    continue
                if response.status_code == 404:
                    logger.warning('{} 404 Not Found'.format(file_url))
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
                        response.encoding = 'utf-8'
                    yield file_url
                    try:
                        for line in response.iter_lines():
                            # filter out keep-alive newlines
                            if line:
                                line = line.decode('utf-8')
                                yield line
                        # Stop the iterator
                        return
                    except requests.exceptions.ContentDecodingError as exc:
                        logger.warning(
                            '{!r} when downloading {}'.format(
                                exc,
                                source,
                            )
                        )
                        continue
                else:
                    logger.warning('{} {} ({})'.format(
                        source,
                        response.status_code,
                        response.content,
                    ))
                    raise SymbolDownloadError(
                        response.status_code,
                        str(source)
                    )

        raise SymbolNotFound(symbol, debugid, filename)

    def has_symbol(self, symbol, debugid, filename):
        """return True if the symbol can be found, False if not
        found in any of the URLs provided."""
        return bool(self._get(symbol, debugid, filename))

    def get_symbol_url(self, symbol, debugid, filename):
        """return the redirect URL or None. If we return None
        it means we can't find the object in any of the URLs provided."""
        found = self._get(symbol, debugid, filename)
        if found:
            if 'url' in found:
                return found['url']

            # If a URL wasn't returned, the bucket it was found in
            # was not public.
            bucket_name = found['bucket_name']
            key = found['key']
            # generate_presigned_url() actually works for both private
            # and public buckets.
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': key,
                },
                # Left commented-in to remind us of what the default is
                # ExpiresIn=3600
            )

    def get_symbol_stream(self, symbol, debugid, filename):
        """return a body stream for download if the file can be found.
        The object is a regular Python generator.
        The first item in the generator is always the URL or the
        (bucketname, objectkey) tuple if found."""
        return self._get_stream(symbol, debugid, filename)
