# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from celery import shared_task
from django.utils import timezone

from tecken.upload.models import UploadsCreated


@shared_task
def update_uploads_created_task(date=None):
    UploadsCreated.update(date or timezone.now().date())
