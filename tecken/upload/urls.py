# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views


app_name = 'upload'

urlpatterns = [
    url(
        r'search/$',
        views.search,
        name='search'
    ),
    url(
        r'upload/(?P<id>\d+)/$',
        views.upload,
        name='upload'
    ),
    url(
        r'',
        views.upload_archive,
        name='upload_archive'
    ),
]
