import logging
from functools import partial

from django import http
from django.contrib import auth
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from .models import Token


logger = logging.getLogger('tecken')


def has_perm(all, codename, obj=None):
    codename = codename.split('.', 1)[1]
    return all.filter(codename=codename).exists()


class APITokenAuthenticationMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if not settings.ENABLE_TOKENS_AUTHENTICATION:  # pragma: no cover
            logger.warn('API Token authentication disabled')
            return
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
        user.has_perm = partial(has_perm, token.permissions.all())
        # User is valid. Set request.user and persist user in the session
        # by logging the user in.
        request.user = user
        auth.login(request, user)
