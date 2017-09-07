# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views


app_name = 'benchmarking'


urlpatterns = [
    url(
        r'caching-vs-boto/$',
        views.caching_vs_boto,
        name='caching_vs_boto'
    ),
]
