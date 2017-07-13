# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import json
import time

from django import http
from django.template import TemplateDoesNotExist, loader
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.conf import settings

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

    user = {}
    if request.user.is_authenticated:
        user['email'] = request.user.email
        user['active'] = request.user.is_active
        user['sign_out_url'] = request.build_absolute_uri(
            reverse('oidc_logout')
        )
    else:
        user['sign_in_url'] = request.build_absolute_uri(
            reverse('oidc_authentication_init')
        )

    context = {
        'user': user,
        'documentation': 'https://tecken.readthedocs.io',
    }
    return http.JsonResponse(context)


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


@require_safe
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
