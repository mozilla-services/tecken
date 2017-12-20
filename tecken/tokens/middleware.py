# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from functools import partial

from django.contrib import auth
from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed, PermissionDenied

from .models import Token


logger = logging.getLogger('tecken')


def has_perm(all, codename, obj=None):
    codename = codename.split('.', 1)[1]
    return all.filter(codename=codename).count()


class APITokenAuthenticationMiddleware:

    def __init__(self, get_response=None):
        if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
            logger.warning('API Token authentication disabled')
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        return response

    def process_request(self, request):
        key = request.META.get('HTTP_AUTH_TOKEN')
        if not key:
            return

        try:
            token = Token.objects.select_related('user').get(key=key)
            if token.is_expired:
                raise PermissionDenied('API Token found but expired')
        except Token.DoesNotExist:
            raise PermissionDenied('API Token not matched')

        user = token.user
        if not user.is_active:
            raise PermissionDenied('API Token matched but user not active')

        # It actually doesn't matter so much which backend
        # we use as long as it's something.
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        # Overwrite the has_perm method so that it's restricted to only
        # the permission that the Token object specifies.
        user.has_perm = partial(has_perm, token.permissions.all())
        # User is valid. Set request.user and persist user in the session
        # by logging the user in.
        request.user = user
        auth.login(request, user)
