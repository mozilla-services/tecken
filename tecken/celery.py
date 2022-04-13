# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# FIXME(willkg): 1728210: remove this after we remove celery infra
import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tecken.settings")


app = Celery("tecken")


# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
