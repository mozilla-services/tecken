# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import markus

from django import http
from django.conf import settings
from django.views.decorators.http import require_http_methods

from tecken.base.symboldownloader import SymbolDownloader

logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


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
    return http.HttpResponseNotFound()
