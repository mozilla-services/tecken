# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views

urlpatterns = [
    url(
        r'missingsymbols.csv$',
        views.missing_symbols_csv,
        name='missing_symbols_csv'
    ),
    # Legacy URLs where the product name was prefixed by the symbol name.
    # Note how the product name is specific and ignored.
    url(
        r'^(firefox|seamonkey|sunbird|thunderbird|xulrunner|fennec|b2g)/'
        r'(?P<symbol>[^/]+)/(?P<debugid>[0-9A-Fa-f]+)/(?P<filename>.*)',
        views.download_symbol,
        name='download_symbol_legacy'
    ),
    url(
        r'^(?P<symbol>[^/]+)/(?P<debugid>[0-9A-Fa-f]+)/(?P<filename>.*)',
        views.download_symbol,
        name='download_symbol'
    ),
]
