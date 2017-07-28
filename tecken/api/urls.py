# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views


app_name = 'api'

urlpatterns = [
    url(
        r'auth/$',
        views.auth,
        name='auth'
    ),
    url(
        r'tokens/$',
        views.tokens,
        name='tokens'
    ),
    url(
        r'stats/$',
        views.stats,
        name='stats'
    ),
    url(
        r'tokens/(?P<id>\d+)$',
        views.delete_token,
        name='delete_token'
    ),
    url(
        r'uploads/$',
        views.uploads,
        name='uploads'
    ),
    url(
        r'uploads/files$',
        views.upload_files,
        name='upload_files'
    ),
    url(
        r'uploads/upload/(?P<id>\d+)$',
        views.upload,
        name='upload'
    ),
    url(
        r'users/$',
        views.users,
        name='users'
    ),
    url(
        r'users/(?P<id>\d+)$',
        views.edit_user,
        name='edit_user'
    ),
]
