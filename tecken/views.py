# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from pathlib import Path

from django import http
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_control, never_cache
from django.core.cache import cache
from django.shortcuts import redirect
from django.conf import settings

from tecken.base.decorators import api_require_safe


@csrf_exempt
def dashboard(request):
    absolute_url = request.build_absolute_uri()
    if (
        absolute_url.endswith(settings.LOGIN_REDIRECT_URL) and settings.DEBUG
    ):  # pragma: no cover
        return redirect("http://localhost:3000" + settings.LOGIN_REDIRECT_URL)

    return frontend_index_html(request)


def handler500(request):
    return http.JsonResponse({"error": "Internal Server Error"}, status=500)


def handler400(request, exception):
    return http.JsonResponse({"error": str(exception)}, status=400)


def handler403(request, exception):
    return http.JsonResponse(
        {
            # The reason for this 'or' fallback is if somewhere in the code
            # there's a plain `raise PermissionDenied` without a parameter.
            # If that is the case it's slightly nicer to at least return
            # the word 'Forbidden'.
            "error": str(exception)
            or "Forbidden"
        },
        status=403,
    )


def handler404(request, exception):
    context = {"error": "Not Found"}
    if isinstance(exception.args[0], str):
        # It was called like this: `raise Http404('Some Message Here')`
        # For example, if you use `get_object_or_404(Token, id=id)`
        # that shortcut function will raise the string message it
        # gets from the `tecken.tokens.models.DoesNotExist` exception.
        # In this case, use this error message instead.
        context["error"] = exception.args[0]
    else:
        path = exception.args[0]["path"]
        context["path"] = f"/{path}"
    return http.JsonResponse(context, status=404)


def csrf_failure(request, reason=""):
    return http.JsonResponse(
        {"error": reason or "CSRF failure", "csrf_error": True}, status=403
    )


@api_require_safe
def contribute_json(request):
    """Services the contribute.json file as JSON"""
    path = Path(settings.BASE_DIR) / "contribute.json"
    data = path.open("rb")
    return http.FileResponse(data)


@cache_control(max_age=60 * 60 * (not settings.DEBUG))
def frontend_index_html(request, path="/"):
    if request.path_info == "/index.html":
        # remove the static file mention
        return redirect("/")
    index_path = Path(settings.STATIC_ROOT) / "index.html"
    data = index_path.open("rb")
    return http.FileResponse(data)


@never_cache
def auth_debug(request):
    """Helps to check that server-client relationship is sensible.

    If, in some environment, you can authenticate it might be because cookies don't work
    or the server cache is busted.
    """
    out = []
    if cache.get("auth_debug"):
        out.append("Cache works!")
    else:
        cache.set("auth_debug", True, 10)
        out.append("Refresh to see if caching works.")

    if request.session.get("auth_debug"):
        out.append("Session cookies work!")
    else:
        request.session["auth_debug"] = True
        out.append("Refresh to see if session cookies work.")

    return http.HttpResponse(
        "\n".join([""] + out), content_type="text/plain; charset=utf-8"
    )


def broken_view(request):
    """Raises an unhandled exception to test Sentry.

    Always have this behind some kind of basicauth.

    """
    raise Exception("Intentional exception")
