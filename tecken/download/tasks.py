# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import markus
from celery import shared_task

from django.db import OperationalError

from tecken.download.utils import store_missing_symbol


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


@shared_task(autoretry_for=(OperationalError,))
def store_missing_symbol_task(*args, **kwargs):
    """Task for fire-and-forget logging of missing symbol."""
    store_missing_symbol(*args, **kwargs)
