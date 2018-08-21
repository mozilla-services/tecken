# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from tempfile import TemporaryDirectory
from functools import wraps

from django import http
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils.decorators import available_attrs
from django.contrib.auth.decorators import permission_required, user_passes_test

logger = logging.getLogger("tecken")


def api_login_required(view_func):
    """similar to django.contrib.auth.decorators.login_required
    except instead of redirecting it returns a 403 message if not
    authenticated."""

    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_active:
            error_msg = "This requires an Auth-Token to authenticate the request"
            if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
                error_msg += " (ENABLE_TOKENS_AUTHENTICATION is False)"
            raise PermissionDenied(error_msg)
        return view_func(request, *args, **kwargs)

    return inner


def api_permission_required(perm):
    """Slight override on django.contrib.auth.decorators.permission_required
    that forces the `raise_exception` to be set to True.
    """
    return permission_required(perm, raise_exception=True)


def api_any_permission_required(*perms):
    """Allow the user through if the user has any of the provided
    permissions. If none, raise a PermissionDenied error.

    Also, unlike the django.contrib.auth.decorators.permission_required,
    in this one we hardcode it to raise PermissionDenied if the
    any-permission check fails.
    """

    def check_perms(user):
        # First check if the user has the permission (even anon users)
        for perm in perms:
            if user.has_perm(perm):
                return True
        raise PermissionDenied

    return user_passes_test(check_perms)


def api_superuser_required(view_func):
    """Decorator that will return a 403 JSON response if the user
    is *not* a superuser.
    Use this decorator *after* others like api_login_required.
    """

    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_superuser:
            error_msg = "Must be superuser to access this view."
            raise PermissionDenied(error_msg)
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
        trueish = ("1", "true", "yes")
        debug = request.META.get("HTTP_DEBUG", "").lower() in trueish
        request._request_debug = debug
        return view_func(request, *args, **kwargs)

    return wrapper


class JsonHttpResponseNotAllowed(http.JsonResponse):
    status_code = 405

    def __init__(self, permitted_methods, data, *args, **kwargs):
        super(JsonHttpResponseNotAllowed, self).__init__(data, *args, **kwargs)
        self["Allow"] = ", ".join(permitted_methods)


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
                message = f"Method Not Allowed ({request.method}): {request.path}"
                logger.warning(message, extra={"status_code": 405, "request": request})
                return JsonHttpResponseNotAllowed(
                    request_method_list, {"error": message}
                )
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


def set_cors_headers(origin="*", methods="GET"):
    """Decorator function that sets CORS headers on the response."""
    if isinstance(methods, str):
        methods = [methods]

    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            response = func(*args, **kwargs)
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = ",".join(methods)
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
