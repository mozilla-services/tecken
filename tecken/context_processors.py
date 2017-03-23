# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import os

from django.conf import settings as django_settings
from django.contrib import messages
from django.utils.safestring import mark_safe


def settings(request):
    """
    Adds static-related context variables to the context.
    """
    return {'settings': django_settings}


def version(request):
    """
    Adds static-related context variables to the context.
    """
    heroku_slug_commit = os.environ.get('HEROKU_SLUG_COMMIT', None)
    response = {}
    if django_settings.VERSION:
        response = {
            'version': django_settings.VERSION.get('version', None),
        }
        commit = django_settings.VERSION.get('commit')
        if commit:
            response['commit'] = commit[:7]
        elif heroku_slug_commit:
            response['commit'] = heroku_slug_commit[:7]
    return response


def alerts(request):
    """
    Here be dragons, for who are bold enough to break systems and lose data
    """
    host = request.get_host()
    warning = """
        <h4>Here be dragons!</h4>
        This service is currently under development and may not be stable."""
    if any(hint in host for hint in ['stag', 'localhost', 'dev']):
        messages.warning(request, mark_safe(warning))
    return {}
