# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# from django.contrib.auth.decorators import login_required
from django.http import HttpResponseServerError
from django.template import Context, TemplateDoesNotExist, loader
from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt
# from django.views.decorators.csrf import requires_csrf_token
# from guardian.shortcuts import get_objects_for_user

from .symbolicate.views import symbolicate_json

# @login_required
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


# @requires_csrf_token
def server_error(request, template_name='500.html'):
    """
    500 error handler.

    Templates: :template:`500.html`
    Context: None
    """
    try:
        template = loader.get_template(template_name)
    except TemplateDoesNotExist:
        return HttpResponseServerError(
            '<h1>Server Error (500)</h1>',
            content_type='text/html'
        )
    return HttpResponseServerError(template.render(Context({
        'request': request,
    })))
