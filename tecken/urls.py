# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
# from django.contrib.auth.decorators import login_required
from django.views import generic, static

from . import views

handler500 = 'tecken.views.server_error'

# require login before visiting the admin, to enforce django-allauth
# admin.site.login = login_required(admin.site.login)

urlpatterns = [
    url(r'^$', views.dashboard, name='dashboard'),

    url(r'symbolicate/', include('tecken.symbolicate.urls')),
    # url(r'^admin/rq/', include('django_rq.urls')),
    # url(r'^admin/', include(admin.site.urls)),
    #
    # url(r'clusters/', include('atmo.clusters.urls')),
    # url(r'jobs/', include('atmo.jobs.urls')),
    # url(r'keys/', include('atmo.keys.urls')),
    # url(r'whatsnew/', include('atmo.whatsnew.urls')),

    # contribute.json url
    url(
        r'^(?P<path>contribute\.json)$',
        static.serve,
        {'document_root': settings.BASE_DIR}
    ),
    url(r'^404/$', generic.TemplateView.as_view(template_name='404.html')),
    url(r'^500/$', generic.TemplateView.as_view(template_name='500.html')),

    # url(r'^accounts/', include('allauth.urls')),
]
