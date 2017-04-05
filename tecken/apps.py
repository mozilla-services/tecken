# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging

from django.apps import AppConfig


logger = logging.getLogger('django')


class TeckenAppConfig(AppConfig):
    name = 'tecken'

    def ready(self):
        # The app is now ready.
        pass
