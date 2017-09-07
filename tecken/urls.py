# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os

from django.conf import settings
from django.conf.urls import include, url
from django.views import static

from . import views

# These handlers are for dealing with exceptions raised from within
# Django. Most other 4xx errors happen explicitly in the view functions.
handler500 = 'tecken.views.handler500'
handler400 = 'tecken.views.handler400'
handler403 = 'tecken.views.handler403'
handler404 = 'tecken.views.handler404'


urlpatterns = [
    url(r'^$', views.dashboard, name='dashboard'),
    url(r'^__task_tester__$', views.task_tester, name='task_tester'),
    url(
        r'symbolicate/',
        include('tecken.symbolicate.urls', namespace='symbolicate')
    ),
    url(r'^oidc/', include('mozilla_django_oidc.urls')),
    url(
        r'upload/',
        include('tecken.upload.urls', namespace='upload')
    ),
    url(
        r'api/',
        include('tecken.api.urls', namespace='api')
    ),
    url(
        r'__benchmarking__/',
        include('tecken.benchmarking.urls', namespace='benchmarking')
    ),
    url(
        r'',
        include('tecken.download.urls', namespace='download')
    ),
    url(
        r'^contribute\.json$',
        views.contribute_json,
        name='contribute_json'
    ),
    url(
        r'^(?P<path>favicon.ico)$',
        static.serve,
        {'document_root': os.path.join(settings.BASE_DIR, 'favicons')}
    ),
]
