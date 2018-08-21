# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger("django")


def attach_token_permissions(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission

    # There are certain groups that make no sense if they don't also
    # have the 'manage_tokens' permission.
    names = ("Uploaders", "Upload Auditors")
    for group in Group.objects.filter(name__in=names):
        group.permissions.add(Permission.objects.get(codename="manage_tokens"))


class TokensAppConfig(AppConfig):
    name = "tecken.tokens"

    def ready(self):
        post_migrate.connect(attach_token_permissions, sender=self)
