# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import time

from django import http
from django.template import TemplateDoesNotExist, loader
from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from .symbolicate.views import symbolicate_json
from tecken.tasks import sample_task


@csrf_exempt
def dashboard(request):
    # Ideally people should...
    # `HTTP -X POST -d JSON http://hostname/symbolicate/`
    # But if they do it directly on the root it should still work,
    # for legacy reasons.
    if request.method == 'POST' and request.body:
        return symbolicate_json(request)

    context = {}
    return TemplateResponse(request, 'tecken/dashboard.html', context=context)


def server_error(request, template_name='500.html'):
    """
    500 error handler.

    Templates: :template:`500.html`
    Context: None
    """
    try:
        template = loader.get_template(template_name)
    except TemplateDoesNotExist:
        return http.HttpResponseServerError(
            '<h1>Server Error (500)</h1>',
            content_type='text/html'
        )
    return http.HttpResponseServerError(template.render({
        'request': request,
    }))


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
