# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from functools import partial

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import MiddlewareNotUsed, PermissionDenied

from .models import Token


logger = logging.getLogger("tecken")


def has_perm(all, codename, obj=None):
    codename = codename.split(".", 1)[1]
    return all.filter(codename=codename).count()


class APITokenAuthenticationMiddleware:
    def __init__(self, get_response=None):
        if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
            logger.warning("API Token authentication disabled")
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        return response

    def force_full_request_body_read(self, request):
        """Force the read for the entire request body

        The client may be using chunked encoding transfer. This forces Tecken
        to read the entire request body before sending a response. Otherwise
        nginx will close the connection and the client won't get the response.

        See bug 1655944.

        """
        content_length = request.META.get("content-length", 0)
        if content_length == 0:
            return

        total_size = 0
        try:
            while total_size < content_length:
                size = len(request.read())
                total_size += size
            logging.debug(
                "draining request body because of token problem; %d", total_size
            )
        except Exception as exc:
            logging.info("exception thrown when draining request body: %r", exc)

    def process_request(self, request):
        key = request.META.get("HTTP_AUTH_TOKEN")
        if not key:
            return

        try:
            token = Token.objects.select_related("user").get(key=key)
            if token.is_expired:
                self.force_full_request_body_read(request)
                raise PermissionDenied("API Token found but expired")
        except Token.DoesNotExist:
            self.force_full_request_body_read(request)
            raise PermissionDenied("API Token not matched")

        user = token.user
        if not user.is_active:
            self.force_full_request_body_read(request)
            raise PermissionDenied("API Token matched but user not active")

        # Overwrite the has_perm method so that it's restricted to only
        # the permission that the Token object specifies.
        user.has_perm = partial(has_perm, token.permissions.all())
        # User is valid. Set request.user and persist user in the request
        # by logging the user in.
        request.user = user
        user_logged_in.send(sender=user.__class__, request=request, user=user)
