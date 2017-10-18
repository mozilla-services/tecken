# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import hashlib
from tempfile import TemporaryDirectory
from functools import wraps

from django import http
from django.conf import settings
from django.utils.decorators import available_attrs
from django.contrib.auth.decorators import permission_required
from django.core.cache import cache
from django.utils.encoding import force_text, force_bytes

logger = logging.getLogger('tecken')


def api_login_required(view_func):
    """similar to django.contrib.auth.decorators.login_required
    except instead of redirecting it returns a 403 message if not
    authenticated."""
    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_active:
            error_msg = (
                'This requires an Auth-Token to authenticate the request'
            )
            if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
                error_msg += ' (ENABLE_TOKENS_AUTHENTICATION is False)'
            return http.JsonResponse({'error': error_msg}, status=403)
        return view_func(request, *args, **kwargs)

    return inner


def api_permission_required(perm):
    """Slight override on django.contrib.auth.decorators.permission_required
    that forces the `raise_exception` to be set to True.
    """
    return permission_required(perm, raise_exception=True)


def api_superuser_required(view_func):
    """Decorator that will return a 403 JSON response if the user
    is *not* a superuser.
    Use this decorator *after* others like api_login_required.
    """
    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_superuser:
            error_msg = (
                'Must be superuser to access this view.'
            )
            return http.JsonResponse({'error': error_msg}, status=403)
        return view_func(request, *args, **kwargs)

    return inner


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


def cache_memoize(
    timeout,
    prefix=None,
    args_rewrite=None,
    hit_callable=None,
    miss_callable=None,
    store_result=True,
):
    """Decorator for memoizing function calls where we use the
    "local cache" to store the result.

    :arg int time: Number of seconds to store the result if not None
    :arg string prefix: If None becomes the function name.
    :arg function args_rewrite: Callable that rewrites the args first useful
    if your function needs nontrivial types but you know a simple way to
    re-represent them for the sake of the cache key.
    :arg function hit_callable: Gets executed if key was in cache.
    :arg function miss_callable: Gets executed if key was *not* in cache.
    :arg bool store_result: If you know the result is not important, just
    that the cache blocked it from running repeatedly, set this to False.

    Usage::

        @cache_memoize(
            300,  # 5 min
            args_rewrite=lambda user: user.email,
            hit_callable=lambda: print("Cache hit!"),
            miss_callable=lambda: print("Cache miss :("),
        )
        def hash_user_email(user):
            dk = hashlib.pbkdf2_hmac('sha256', user.email, b'salt', 100000)
            return binascii.hexlify(dk)

    Or, when you don't actually need the result, useful if you know it's not
    valuable to store the execution result::

        @cache_memoize(
            300,  # 5 min
            store_result=False,
        )
        def send_email(email):
            somelib.send(email, subject="You rock!", ...)

    Also, whatever you do where things get cached, you can undo that.
    For example::

        @cache_memoize(100)
        def callmeonce(arg1):
            print(arg1)

        callmeonce('peter')  # will print 'peter'
        callmeonce('peter')  # nothing printed
        callmeonce.invalidate('peter')
        callmeonce('peter')  # will print 'peter'

    Suppose you know for good reason you want to bypass the cache and
    really let the decorator let you through you can set one extra
    keyword argument called `_refresh`. For example::

        @cache_memoize(100)
        def callmeonce(arg1):
            print(arg1)

        callmeonce('peter')                 # will print 'peter'
        callmeonce('peter')                 # nothing printed
        callmeonce('peter', _refresh=True)  # will print 'peter'

    """

    if args_rewrite is None:
        def noop(*args):
            return args
        args_rewrite = noop

    def decorator(func):

        def _make_cache_key(*args, **kwargs):
            cache_key = ':'.join(
                [force_text(x) for x in args_rewrite(*args)] +
                [force_text(f'{k}={v}') for k, v in kwargs.items()]
            )
            return hashlib.md5(force_bytes(
                'cache_memoize' + (prefix or func.__name__) + cache_key
            )).hexdigest()

        @wraps(func)
        def inner(*args, **kwargs):
            refresh = kwargs.pop('_refresh', False)
            cache_key = _make_cache_key(*args, **kwargs)
            if refresh:
                result = None
            else:
                result = cache.get(cache_key)
            if result is None:
                result = func(*args, **kwargs)
                if not store_result:
                    # Then the result isn't valuable/important to store but
                    # we want to store something. Just to remember that
                    # it has be done.
                    cache.set(cache_key, True, timeout)
                elif result is not None:
                    cache.set(cache_key, result, timeout)
                if miss_callable:
                    miss_callable(*args, **kwargs)
            elif hit_callable:
                hit_callable(*args, **kwargs)
            return result

        def invalidate(*args, **kwargs):
            cache_key = _make_cache_key(*args, **kwargs)
            cache.delete(cache_key)

        inner.invalidate = invalidate
        return inner

    return decorator


def set_cors_headers(origin='*', methods='GET'):
    """Decorator function that sets CORS headers on the response."""
    if isinstance(methods, str):
        methods = [methods]

    def decorator(func):

        @wraps(func)
        def inner(*args, **kwargs):
            response = func(*args, **kwargs)
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Methods'] = ','.join(methods)
            return response

        return inner

    return decorator


def make_tempdir(prefix=None, suffix=None):
    """Decorator that adds a last argument that is the path to a temporary
    directory that gets deleted after the function has finished.

    Usage::

        @make_tempdir()
        def some_function(arg1, arg2, tempdir, kwargs1='one'):
            assert os.path.isdir(tempdir)
            ...
    """

    def decorator(func):

        @wraps(func)
        def inner(*args, **kwargs):
            with TemporaryDirectory(prefix=prefix, suffix=suffix) as f:
                args = args + (f,)
                return func(*args, **kwargs)

        return inner

    return decorator
