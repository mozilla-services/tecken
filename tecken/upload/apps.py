# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger('django')


# XXX Is this needed any more? Aren't all things done by explicit permissions?
def create_default_groups(sender, **kwargs):
    # Make sure there's a group for uploaders.
    # And if the group didn't exist, make sure it has the "Can add upload"
    # permission.
    from django.contrib.auth.models import Group, Permission
    try:
        Group.objects.get(name='Uploaders')
    except Group.DoesNotExist:
        group = Group.objects.create(name='Uploaders')
        group.permissions.add(
            Permission.objects.get(codename='upload_symbols')
        )
        logger.info('Group "Uploaders" created')


class UploadAppConfig(AppConfig):
    name = 'tecken.upload'

    def ready(self):
        post_migrate.connect(create_default_groups, sender=self)
