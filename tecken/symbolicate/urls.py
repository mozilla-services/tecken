# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf.urls import url

from . import views

urlpatterns = [
    url(
        r'__hit_ratio__',
        views.hit_ratio,
        name='hit_ratio'
    ),

    # must be last
    url(
        r'',
        views.symbolicate_json,
        name='symbolicate_json'
    ),

]
