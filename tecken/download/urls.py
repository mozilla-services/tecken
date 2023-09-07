# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import register_converter, path

from tecken.download import views


class _Converter:
    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class MixedCaseHexConverter(_Converter):
    regex = "[0-9A-Fa-f]+"


register_converter(MixedCaseHexConverter, "hex")


app_name = "download"

urlpatterns = [
    path(
        "try/<str:debugfilename>/<hex:debugid>/<str:filename>",
        views.download_symbol_try,
        name="download_symbol_try",
    ),
    path(
        "<str:debugfilename>/<hex:debugid>/<str:filename>",
        views.download_symbol,
        name="download_symbol",
    ),
]
