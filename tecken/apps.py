# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging

# import redis
# import session_csrf
from django.apps import AppConfig
# from django.utils.module_loading import import_string

# DEFAULT_JOB_TIMEOUT = 15

logger = logging.getLogger("django")


class TeckenAppConfig(AppConfig):
    name = 'tecken'

    def ready(self):
        # The app is now ready. Include any monkey patches here.
        pass

        # # Monkey patch CSRF to switch to session based CSRF. Session
        # # based CSRF will prevent attacks from apps under the same
        # # domain. If you're planning to host your app under it's own
        # # domain you can remove session_csrf and use Django's CSRF
        # # library. See also
        # # https://github.com/mozilla/sugardough/issues/38
        # session_csrf.monkeypatch()
        #
        # # Register rq scheduled jobs, if Redis is available
        # try:
        #     connection = django_rq.get_connection('default')
        #     connection.ping()
        # except redis.ConnectionError:
        #     logger.warning('Could not connect to Redis, not reigstering RQ jobs')
        # else:
        #     register_job_schedule()
        #
