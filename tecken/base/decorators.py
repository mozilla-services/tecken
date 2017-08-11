# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import hashlib
from functools import wraps

from django import http
from django.utils.decorators import available_attrs
from django.contrib.auth.decorators import permission_required
from django.core.cache import caches
from django.utils.encoding import force_text, force_bytes

logger = logging.getLogger('tecken')


def api_login_required(view_func):
    """similar to django.contrib.auth.decorators.login_required
    except instead of redirecting it returns a 403 message if not
    authenticated."""
    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_active:
            return http.JsonResponse(
                {'error': (
                    'This requires an Auth-Token to authenticate the request'
                )},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return inner


def api_permission_required(perm):
    """Slight override on django.contrib.auth.decorators.permission_required
    that forces the `raise_exception` to be set to True.
    """
    return permission_required(perm, raise_exception=True)


def set_request_debug(view_func):
    """When you use this decorator, the request object gets changed.
    The request gets a new boolean attribute set to either True or False
    called `_debug_request` if and only if the request has a header
    'HTTP_DEBUG' that is 'True', 'Yes' or '1' (case insensitive).

    Usage:

        @set_request_debug
        def myview(request):
            debug = request._request_debug
            assert debug in (True, False)
            return http.HttpResponse(debug)
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        trueish = ('1', 'true', 'yes')
        debug = request.META.get('HTTP_DEBUG', '').lower() in trueish
        request._request_debug = debug
        return view_func(request, *args, **kwargs)

    return wrapper


class JsonHttpResponseNotAllowed(http.JsonResponse):
    status_code = 405

    def __init__(self, permitted_methods, data, *args, **kwargs):
        super(JsonHttpResponseNotAllowed, self).__init__(data, *args, **kwargs)
        self['Allow'] = ', '.join(permitted_methods)


def api_require_http_methods(request_method_list):
    """
    This is copied verbatim from django.views.decorators.require_http_methods
    *except* it changes which HTTP response class to return.
    All of this just to make it possible to always return a JSON response
    when the request method is not allowed.
    Also, it's changed to use the f'' string format.
    """
    def decorator(func):
        @wraps(func, assigned=available_attrs(func))
        def inner(request, *args, **kwargs):
            if request.method not in request_method_list:
                message = (
                    f'Method Not Allowed ({request.method}): {request.path}'
                )
                logger.warning(
                    message,
                    extra={'status_code': 405, 'request': request}
                )
                return JsonHttpResponseNotAllowed(request_method_list, {
                    'error': message,
                })
            return func(request, *args, **kwargs)
        return inner
    return decorator


api_require_GET = api_require_http_methods(["GET"])
api_require_GET.__doc__ = (
    "Decorator to require that a view only accepts the GET method."
)

api_require_POST = api_require_http_methods(["POST"])
api_require_POST.__doc__ = (
    "Decorator to require that a view only accepts the POST method."
)

api_require_safe = api_require_http_methods(["GET", "HEAD"])
api_require_safe.__doc__ = (
    "Decorator to require that a view only accepts safe methods: GET and HEAD."
)


def local_cache_memoize_void(timeout):
    """Decorator for memoizing function calls that don't return anything.
    Meaning, it only runs once per arguments + keyword arguments as a
    cache key.

    For example:

        >>> from tecken.base.decorators import local_cache_memoize_void
        >>> @local_cache_memoize_void(10)
        ... def runmeonce(a, b, k='bla'):
        ...     print((a, b, k))
        ...
        >>> runmeonce(1, 2)
        (1, 2, 'bla')
        >>> runmeonce(1, 2)
        >>> runmeonce(1, 2, k=1.0)
        (1, 2, 1.0)
        >>> runmeonce(1, 2, k=1.0)
        >>> runmeonce(1, 2, k=1.1)
        (1, 2, 1.1)
        >>> runmeonce(1, 'fö')
        (1, 'fö', 'bla')
        >>> runmeonce(1, 'fö')

    Note how it only prints if the arguments are different.
    """

    def decorator(func):
        # The local cache is the memcached service that is expected to
        # run on the same server as the webapp.
        local_cache = caches['local']

        @wraps(func)
        def inner(*args, **kwargs):
            cache_key = ':'.join(
                [force_text(x) for x in args] +
                [force_text(f'{k}={v}') for k, v in kwargs.items()]
            )
            cache_key = hashlib.md5(force_bytes(cache_key)).hexdigest()
            if local_cache.get(cache_key) is None:
                func(*args, **kwargs)
                local_cache.set(cache_key, True, timeout)

        return inner

    return decorator
