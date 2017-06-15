# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from functools import wraps

from django import http
from django.contrib.auth.decorators import permission_required


def api_login_required(view_func):
    """similar to django.contrib.auth.decorators.login_required
    except instead of redirecting it returns a 403 message if not
    authenticated."""
    @wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_active:
            return http.HttpResponseForbidden(
                "This requires an Auth-Token to authenticate the request"
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
