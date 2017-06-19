import logging

from django import http
from django.contrib import auth
from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.utils.deprecation import MiddlewareMixin

from .models import Token


logger = logging.getLogger('tecken')


class APITokenAuthenticationMiddleware(MiddlewareMixin):

    def __init__(self):
        if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
            logger.warn('API Token authentication disabled')
            raise MiddlewareNotUsed

    def process_request(self, request):

        key = request.META.get('HTTP_AUTH_TOKEN')
        if not key:
            return

        try:
            token = Token.objects.select_related('user').get(key=key)
            if token.is_expired:
                # XXX change to one that produces JSON
                return http.HttpResponseForbidden(
                    'API Token found but expired'
                )
        except Token.DoesNotExist:
            # XXX change to one that produces JSON
            return http.HttpResponseForbidden(
                'API Token not matched'
            )

        user = token.user
        if not user.is_active:
            # XXX change to one that produces JSON
            return http.HttpResponseForbidden(
                'API Token matched but user not active'
            )

        # It actually doesn't matter so much which backend
        # we use as long as it's something.
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        # User is valid. Set request.user and persist user in the session
        # by logging the user in.
        request.user = user
        auth.login(request, user)
