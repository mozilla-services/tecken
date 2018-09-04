# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import json
import time

from django import http
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_control, never_cache
from django.core.cache import cache
from django.shortcuts import redirect
from django.conf import settings
from django.views.static import serve

from tecken.base.decorators import api_require_safe
from tecken.tasks import sample_task


@csrf_exempt
def dashboard(request):
    if request.method == "POST" and request.body:
        # We *used* to allow symbolication off the '/' root URL. It was
        # due to legacy when Tecken became a mix of Socorro's symbol upload,
        # Snappy's symbolication, etc.
        # It's time to get out of that habit and start using the right
        # endpoint explicitly.
        return http.HttpResponse(
            "See http://tecken.readthedocs.io/en/latest/symbolication.html",
            status=410,  # Gone
        )

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


@csrf_exempt
def task_tester(request):
    if request.method == "POST":
        cache.set("marco", "ping", 100)
        value = request.POST.get("value", "polo")
        sample_task.delay("marco", value, 10)
        return http.HttpResponse("Now make a GET request to this URL\n", status=201)
    else:
        if not cache.get("marco"):
            return http.HttpResponseBadRequest(
                "Make a POST request to this URL first\n"
            )
        for i in range(3):
            value = cache.get("marco")
            if value == "polo":
                return http.HttpResponse("It works!\n")
            time.sleep(1)

        return http.HttpResponseServerError(
            "Tried 4 times (4 seconds) and no luck :(\n"
        )


@api_require_safe
def contribute_json(request):
    """Advantages of having our own custom view over using
    django.view.static.serve is that we get the right content-type
    and as a view we write a unit test that checks that the JSON is valid
    and can be deserialized."""
    with open(os.path.join(settings.BASE_DIR, "contribute.json")) as f:
        contribute_json_dict = json.load(f)
    return http.JsonResponse(contribute_json_dict, json_dumps_params={"indent": 3})


@cache_control(max_age=60 * 60 * (not settings.DEBUG))
def frontend_index_html(request, path="/"):
    if request.path_info == "/index.html":
        # remove the static file mention
        return redirect("/")
    return serve(request, "/index.html", document_root=settings.STATIC_ROOT)


@never_cache
def auth_debug(request):
    """Helps to check that your server-client relationship is good and sane.
    If, in some environment, you can authenticate it might be because
    cookies don't work or the server cache is busted.
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
