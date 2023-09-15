# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import path

from tecken.download import views


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
