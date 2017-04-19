# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from urllib.parse import urlparse

import requests
import markus


from django import http
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.gzip import gzip_page


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


PROXY_HEADERS = (
    'Content-Length',
    'Last-Modified',
    'Content-TYPE',
    'ETag',
)


@metrics.timer_decorator('download_symbol')
# The gzip_page decorator automatically gzips the content
@gzip_page
@require_http_methods(['GET', 'HEAD'])
def download_symbol(request, symbol, debugid, filename):
    for base_url in settings.SYMBOL_URLS:
        assert base_url.endswith('/')
        url = '{}{}/{}/{}'.format(
            base_url,
            symbol,
            debugid.upper(),
            filename,
        )
        if request.method == 'HEAD':
            response = requests.head(url)
        else:
            # Always download as a stream to reduce memory bloat.
            response = requests.get(url, stream=True)
        if response.status_code == 200:
            if request.method == 'HEAD':
                return http.HttpResponse()

            output = http.HttpResponse()
            # Replicate whitelisted headers from the original request
            # to the final response.
            for header in PROXY_HEADERS:
                if response.headers.get(header):
                    output[header] = response.headers[header]
            total_size = 0
            for line in response:
                output.write(line)
                total_size += len(line)
            metrics.histogram(
                'download_symbols_size',
                total_size,
                tags=[urlparse(url).netloc]
            )
            return output

    raise http.Http404()
