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


def test_local_cache_memoize():

    calls_made = []

    @decorators.local_cache_memoize(10)
    def runmeonce(a, b, k='bla'):
        calls_made.append((a, b, k))
        return '{} {} {}'.format(a, b, k)  # sample implementation

    runmeonce(1, 2)
    runmeonce(1, 2)
    assert len(calls_made) == 1
    runmeonce(1, 3)
    assert len(calls_made) == 2
    # should work with most basic types
    runmeonce(1.1, 'foo')
    runmeonce(1.1, 'foo')
    assert len(calls_made) == 3
    # even more "advanced" types
    runmeonce(1.1, 'foo', k=list('åäö'))
    runmeonce(1.1, 'foo', k=list('åäö'))
    assert len(calls_made) == 4
    # And shouldn't be a problem even if the arguments are really long
    runmeonce('A' * 200, 'B' * 200, {'C' * 100: 'D' * 100})
    assert len(calls_made) == 5

    # different prefixes
    @decorators.local_cache_memoize(10, prefix='first')
    def foo(value):
        calls_made.append(value)
        return 'ho'

    @decorators.local_cache_memoize(10, prefix='second')
    def bar(value):
        calls_made.append(value)
        return 'ho'

    foo('hey')
    bar('hey')
    assert len(calls_made) == 7

    # Test when you don't care about the result
    @decorators.local_cache_memoize(10, store_result=False, prefix='different')
    def returnnothing(a, b, k='bla'):
        calls_made.append((a, b, k))
        # note it returns None
    returnnothing(1, 2)
    returnnothing(1, 2)
    assert len(calls_made) == 8
