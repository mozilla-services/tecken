# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from urllib.parse import urlparse

import markus
import boto3
from botocore.exceptions import ClientError

from django import http
from django.conf import settings
from django.views.decorators.http import require_http_methods


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


class SymbolDownloader:
    """
    Class for asking S3 two tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.

    The core functionality is that is supports a *list* of URLs.
    Each URL is a URL that indicates a S3 bucket in the path-style format
    which means that the region is in the domain name, and the bucket name
    is the first part of the URL path.

    There is no distinction between public and non-public
    URLs. For example, if you were to do::

        >>> d = SymbolDownloader([
        ...  'https://s3.example.com/public/',
        ...  'https://s3.example.com/private/',
        ... ])
        >>> d.get_symbol_url(
        ...  'FlashPlayerPlugin.pdb',
        ...  '0052638CDB3E42F98D742155F0D1FB611',
        ...  'FlashPlayerPlugin.pdb'
        ... )
        https://s3-us-west-2.amazonaws.com/private/Flash/0052638CDB3E42F98D742155F0D1FB611/FlashPlayerPlugin.pdb?Expires=12345678...

    Meaning, it will happily give out a public URL to a file in an
    S3 bucket that is not publicy available (i.e. doesn't have static
    website hosting enabled).

    Ideally, determining which URLs to use should be done outside
    this class. E.g.::

        >>> urls = settings.PUBLIC_SYMBOL_URLS
        >>> if requests.user.has_permission('private-bucket'):  # pseudo code
        ...    urls.extend(settings.PRIVATE_SYMBOL_URLS)
        >>> d = SymbolDownloader(urls)

    """
    def __init__(self, urls):
        self.urls = urls
        self.s3_client = boto3.client('s3')

    def _get(self, symbol, debugid, filename):
        # This will automatically pick up credentials from the environment
        # variables to authenticate.

        for url in self.urls:
            # At the moment...
            # We don't have any private buckets configured but the code
            # below will work for private buckets too.
            # e.g. http://localhost:8000/FlashPlayerPlugin.pdb/0052638CDB3E42F98D742155F0D1FB611/FlashPlayerPlugin.pdb  # noqa
            # works if you add the private bucket to settings.SYMBOL_URLS.
            # We also don't have authentication within tecken yet. :)

            # The URL is expected to have the bucket name as the first
            # part of the pathname.
            # In the future we might expand to a more elaborate scheme.
            parsed = urlparse(url)
            try:
                bucket_name, prefix = parsed.path[1:].split('/', 1)
            except ValueError:
                prefix = ''
                bucket_name = parsed.path[1:]
            key = '{}{}/{}/{}'.format(
                prefix,
                symbol,
                # The are some legacy use case where the debug ID might
                # not already be uppercased. If so, we override it.
                # Every debug ID is always in uppercase.
                debugid.upper(),
                filename,
            )
            # By doing a head_object() lookup we will immediately know
            # if the object exists under this URL.
            # It doesn't matter yet if the client of this call is
            # doing a HEAD or a GET. We need to first know if the key
            # exists in this bucket.
            try:
                self.s3_client.head_object(
                    Bucket=bucket_name,
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
            return bucket_name, key

    def has_symbol(self, symbol, debugid, filename):
        """return True if the symbol can be found, False if not
        found in any of the URLs provided."""
        return bool(self._get(symbol, debugid, filename))

    def get_symbol_url(self, symbol, debugid, filename):
        """return the redirect URL or None. If we return None
        it means we can't find the object in any of the URLs provided."""
        found = self._get(symbol, debugid, filename)
        if found:
            bucket_name, key = found
            # Using generate_presigned_url() has the advantage that
            # it works for both private and public buckets.
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': key,
                },
                # Left commented-in to remind us of what the default is
                # ExpiresIn=3600
            )


@metrics.timer_decorator('download_symbol')
@require_http_methods(['GET', 'HEAD'])
def download_symbol(request, symbol, debugid, filename):
    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    if request.method == 'HEAD':
        if downloader.has_symbol(symbol, debugid, filename):
            return http.HttpResponse()
    else:
        url = downloader.get_symbol_url(symbol, debugid, filename)
        if url:
            return http.HttpResponseRedirect(url)
    raise http.Http404()
