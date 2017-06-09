# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os

from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecken.settings')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Localdev')


import configurations  # noqa
configurations.setup()


app = Celery('tecken')


# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Specifically list the apps that have tasks.py
# Note! If not doing this you get a strange RuntimeError
# ('path' must be None or a list, not <class '_frozen_importlib_external._NamespacePath'>)  # noqa
app.autodiscover_tasks(['tecken'])


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
