# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate

from tecken.upload import executor

logger = logging.getLogger("django")


def create_default_groups(sender, **kwargs):
    # Make sure there's a group for uploaders.
    # And if the group didn't exist, make sure it has the "Can add upload"
    # permission.
    from django.contrib.auth.models import Group, Permission

    name = "Uploaders"
    try:
        group = Group.objects.get(name=name)
    except Group.DoesNotExist:
        group = Group.objects.create(name=name)
        group.permissions.add(Permission.objects.get(codename="upload_symbols"))
        logger.info(f'Group "{name}" created')

    # This new permission was added late, and it belongs to the Uploaders
    # group.
    if not group.permissions.filter(codename="upload_try_symbols").exists():
        group.permissions.add(Permission.objects.get(codename="upload_try_symbols"))
        logger.info(f'Adding "upload_try_symbols" to group {name}')

    name = "Upload Auditors"
    try:
        group = Group.objects.get(name=name)
    except Group.DoesNotExist:
        group = Group.objects.create(name=name)
        group.permissions.add(Permission.objects.get(codename="view_all_uploads"))
        logger.info(f'Group "{name}" created')


class UploadAppConfig(AppConfig):
    name = "tecken.upload"

    def ready(self):
        post_migrate.connect(create_default_groups, sender=self)
        executor.init(
            settings.SYNCHRONOUS_UPLOAD_FILE_UPLOAD,
            settings.UPLOAD_FILE_UPLOAD_MAX_WORKERS or None,
        )
