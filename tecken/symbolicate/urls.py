# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.urls import path

from . import views

app_name = 'symbolicate'

urlpatterns = [
    path(
        'v4',
        views.symbolicate_json,
        name='symbolicate_json'
    ),

]
