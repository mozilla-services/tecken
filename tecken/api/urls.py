# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views


app_name = 'api'

"""
Note!
The endpoints that start with a '_' are basically only relevant
for the sake of the frontend. Meaning, it doesn't make sense to use
them in your curl script, for example.
"""

urlpatterns = [
    url(
        r'_auth/$',
        views.auth,
        name='auth'
    ),
    url(
        r'_stats/$',
        views.stats,
        name='stats'
    ),
    url(
        r'tokens/$',
        views.tokens,
        name='tokens'
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
        r'uploads/datasets/$',
        views.uploads_datasets,
        name='uploads_datasets'
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
        r'_users/$',
        views.users,
        name='users'
    ),
    url(
        r'_users/(?P<id>\d+)$',
        views.edit_user,
        name='edit_user'
    ),
    url(
        r'_settings/$',
        views.current_settings,
        name='current_settings'
    ),
]
