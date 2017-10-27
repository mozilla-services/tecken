# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os

import pytest

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


def test_set_cors_headers(rf):

    # Happy patch
    @decorators.set_cors_headers()
    def view_function(request):
        return http.HttpResponse('hello world')

    request = rf.get('/')
    response = view_function(request)
    assert response['Access-Control-Allow-Origin'] == '*'
    assert response['Access-Control-Allow-Methods'] == 'GET'

    # Overrides
    @decorators.set_cors_headers(origin='example.com', methods=['HEAD', 'GET'])
    def view_function(request):
        return http.HttpResponse('hello world')
    response = view_function(request)
    assert response['Access-Control-Allow-Origin'] == 'example.com'
    assert response['Access-Control-Allow-Methods'] == 'HEAD,GET'


def test_make_tempdir():

    mutable = []

    @decorators.make_tempdir(
        prefix='PREFIX',
        suffix='SUFFIX',
    )
    def view_function(request, tmpdir, foo=None):
        assert os.path.isdir(tmpdir)
        basename = os.path.basename(tmpdir)
        assert 'PREFIX' in basename
        assert 'SUFFIX' in basename
        mutable.append(tmpdir)

        if foo == 'ERROR':
            raise NameError('anything')

    view_function('somerequest', foo='bar')
    assert not os.path.isdir(mutable[0])

    # Let it fail this time
    with pytest.raises(NameError):
        view_function('somerequest', foo='ERROR')

    assert not os.path.isdir(mutable[1])
