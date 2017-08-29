# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views


app_name = 'upload'

urlpatterns = [
    url(
        r'^$',
        views.upload_archive,
        name='upload_archive'
    ),
    url(
        r'^download/$',
        views.upload_archive,
        name='upload_by_download_archive'
    ),
]
