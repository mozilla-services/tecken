# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging

import markus
from django_redis import get_redis_connection

from django.conf import settings
from django.apps import AppConfig


logger = logging.getLogger('django')


class TeckenAppConfig(AppConfig):
    name = 'tecken'

    def ready(self):
        # The app is now ready.

        markus.configure(settings.MARKUS_BACKENDS)

        # For some unknown reason, if you don't do at least one read
        # from the Redis connection before you do your first write,
        # you can get a `redis.exceptions.ConnectionError` with
        # "Error 9 while writing to socket. Bad file descriptor."
        # This is only occuring in running unit tests.
        connection = get_redis_connection('default')
        connection.info()

        connection = get_redis_connection('store')
        maxmemory_policy = connection.info()['maxmemory_policy']
        if maxmemory_policy != 'allkeys-lru':  # pragma: no cover
            if settings.DEBUG:
                connection.config_set('maxmemory-policy', 'allkeys-lru')
                logger.warning(
                    "The 'store' Redis cache was not configured to be an "
                    "LRU cache because the maxmemory-policy was set to '{}'. "
                    "Now changed to 'allkeys-lru'.".format(
                        maxmemory_policy,
                    )
                )
            else:
                logger.error(
                    "In production the Redis store HAS to be set to: "
                    "maxmemory-policy=allkeys-lru "
                    "In AWS ElastiCache this is done by setting up "
                    "Parameter Group with maxmemory-policy=allkeys-lru"
                )
