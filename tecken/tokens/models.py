# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import Permission, Group
from django.dispatch import receiver


def make_key():
    return uuid.uuid4().hex


def get_future():
    delta = datetime.timedelta(days=settings.TOKENS_DEFAULT_EXPIRATION_DAYS)
    return timezone.now() + delta


class Token(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    key = models.CharField(max_length=32, default=make_key)
    expires_at = models.DateTimeField(default=get_future)
    permissions = models.ManyToManyField(Permission)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        return self.expires_at < timezone.now()


@receiver(models.signals.m2m_changed, sender=Group.permissions.through)
def drop_permissions_on_group_change(sender, instance, action, **kwargs):
    if action == 'post_remove':
        # A permission was removed from a group.
        # Every Token that had this permission needs to be re-evaluated
        # because, had the user created this token now, they might
        # no longer have access to that permission due to their
        # group memberships.
        permissions = Permission.objects.filter(id__in=kwargs['pk_set'])
        for permission in permissions:
            for token in Token.objects.filter(permissions=permission):
                user_permissions = Permission.objects.filter(
                    group__user=token.user
                )
                if permission not in user_permissions:
                    token.permissions.remove(permission)
