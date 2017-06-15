# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django import http
from django.test import RequestFactory

from tecken.base import decorators


def test_set_request_debug():

    @decorators.set_request_debug
    def myview(request):
        return http.HttpResponse('debug={}'.format(request._request_debug))

    request = RequestFactory().get('/')
    response = myview(request)
    assert response.content == b'debug=False'

    request = RequestFactory(HTTP_DEBUG='true').get('/')
    response = myview(request)
    assert response.content == b'debug=True'

    request = RequestFactory(HTTP_DEBUG='0').get('/')
    response = myview(request)
    assert response.content == b'debug=False'
