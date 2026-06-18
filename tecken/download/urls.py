# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import path, register_converter

from tecken.base.utils import VALID_KEY_CHARS
from tecken.download import views


class KeyComponentConverter:
    regex = VALID_KEY_CHARS

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(KeyComponentConverter, "key")


app_name = "download"

urlpatterns = [
    path(
        "try/<key:debug_file>/<hex:debug_id>/<key:symbols_file>",
        views.download_symbol_try,
        name="download_symbol_try",
    ),
    path(
        "<key:debug_file>/<hex:debug_id>/<key:symbols_file>",
        views.download_symbol,
        name="download_symbol",
    ),
]
