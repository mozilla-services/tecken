# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import json
import time

from django import http
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.shortcuts import redirect
from django.conf import settings

from .symbolicate.views import symbolicate_json
from tecken.base.decorators import api_require_safe
from tecken.tasks import sample_task


@csrf_exempt
def dashboard(request):
    # Ideally people should...
    # `HTTP -X POST -d JSON http://hostname/symbolicate/`
    # But if they do it directly on the root it should still work,
    # for legacy reasons.
    if request.method == 'POST' and request.body:
        return symbolicate_json(request)

    absolute_url = request.build_absolute_uri()
    if (
        absolute_url.endswith(settings.LOGIN_REDIRECT_URL) and
        settings.DEBUG
    ):  # pragma: no cover
        return redirect('http://localhost:3000' + settings.LOGIN_REDIRECT_URL)

    context = {
        'documentation': 'https://tecken.readthedocs.io',
    }
    return http.JsonResponse(context)


def handler500(request):
    return http.JsonResponse({'error': 'Internal Server Error'}, status=500)


def handler400(request):
    return http.JsonResponse({'error': 'Bad Request'}, status=400)


def handler403(request):
    return http.JsonResponse({'error': 'Forbidden'}, status=403)


def handler404(request):
    return http.JsonResponse({'error': 'Not Found'}, status=404)


def csrf_failure(request, reason=''):
    return http.JsonResponse({
        'error': reason or 'CSRF failure',
        'csrf_error': True,
    }, status=403)


@csrf_exempt
def task_tester(request):
    if request.method == 'POST':
        cache.set('marco', 'ping', 100)
        sample_task.delay('marco', 'polo', 10)
        return http.HttpResponse(
            'Now make a GET request to this URL\n',
            status=201,
        )
    else:
        if not cache.get('marco'):
            return http.HttpResponseBadRequest(
                'Make a POST request to this URL first\n'
            )
        for i in range(3):
            value = cache.get('marco')
            if value == 'polo':
                return http.HttpResponse('It works!\n')
            time.sleep(1)

        return http.HttpResponseServerError(
            'Tried 4 times (4 seconds) and no luck :(\n'
        )


@api_require_safe
def contribute_json(request):
    """Advantages of having our own custom view over using
    django.view.static.serve is that we get the right content-type
    and as a view we write a unit test that checks that the JSON is valid
    and can be deserialized."""
    with open(os.path.join(settings.BASE_DIR, 'contribute.json')) as f:
        contribute_json_dict = json.load(f)
    return http.JsonResponse(
        contribute_json_dict,
        json_dumps_params={'indent': 3}
    )
