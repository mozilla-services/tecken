# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from urllib.parse import urlparse

from botocore.exceptions import ClientError
import markus
from django_redis import get_redis_connection

from django.conf import settings
from django.apps import AppConfig

from tecken.s3 import S3Bucket


logger = logging.getLogger("django")


class TeckenAppConfig(AppConfig):
    name = "tecken"

    def ready(self):
        # The app is now ready.

        self._fix_settings_conn_max_age()

        self._configure_markus()

        self._fix_default_redis_connection()

        self._redis_store_eviction_policy()

        self._check_mandatory_settings()

        self._check_s3_urls()

        self._check_upload_s3_url_is_download_s3_url()

    @staticmethod
    def _fix_settings_conn_max_age():
        """Because shortcomings in django-configurations, we can't set
        DATABASES with CONN_MAX_AGE. So let's fix it here.
        """
        if settings.CONN_MAX_AGE:
            settings.DATABASES["default"]["CONN_MAX_AGE"] = settings.CONN_MAX_AGE

    @staticmethod
    def _configure_markus():
        """Must be done once and only once."""
        markus.configure(settings.MARKUS_BACKENDS)

    @staticmethod
    def _fix_default_redis_connection():
        """For some unknown reason, if you don't do at least one read
        from the Redis connection before you do your first write,
        you can get a `redis.exceptions.ConnectionError` with
        "Error 9 while writing to socket. Bad file descriptor."
        This is only occuring in running unit tests.
        But only do this if the caches['default'] isn't a fake one
        redis_client_class = settings.CACHES['default']['OPTIONS'].get(
           'REDIS_CLIENT_CLASS'
        )
        """
        if "LocMemCache" not in settings.CACHES["default"]["BACKEND"]:
            connection = get_redis_connection("default")
            connection.info()

    @staticmethod
    def _redis_store_eviction_policy():
        """Check that the Redis 'store' is configured to have an LRU
        eviction policy.
        In production we assume AWS ElastiCache so we can't do anything
        about it (if it's not set correctly) but issue a logger error.
        In DEBUG mode (i.e. local Docker development), we can actually
        set it here and now.
        """
        connection = get_redis_connection("store")
        maxmemory_policy = connection.info()["maxmemory_policy"]
        if maxmemory_policy != "allkeys-lru":  # pragma: no cover
            if settings.DEBUG:
                connection.config_set("maxmemory-policy", "allkeys-lru")
                logger.warning(
                    "The 'store' Redis cache was not configured to be an "
                    "LRU cache because the maxmemory-policy was set to '{}'. "
                    "Now changed to 'allkeys-lru'.".format(maxmemory_policy)
                )
            else:
                logger.error(
                    "In production the Redis store HAS to be set to: "
                    "maxmemory-policy=allkeys-lru "
                    "In AWS ElastiCache this is done by setting up "
                    "Parameter Group with maxmemory-policy=allkeys-lru"
                )

    @staticmethod
    def _check_s3_urls():
        """If you use minio to functionally test S3, since it's
        ephemeral the buckets you create disappear after a restart.
        Make sure they exist. That's what we expect to happen with the
        real production S3 buckets.
        """
        _all_possible_urls = set(
            list(settings.SYMBOL_URLS)
            + [settings.UPLOAD_DEFAULT_URL, settings.UPLOAD_TRY_SYMBOLS_URL]
            + list(settings.UPLOAD_URL_EXCEPTIONS.values())
        )
        for url in _all_possible_urls:
            if not url or "minio" not in urlparse(url).netloc:
                continue
            bucket = S3Bucket(url)
            try:
                bucket.s3_client.head_bucket(Bucket=bucket.name)
            except ClientError as exception:
                if exception.response["Error"]["Code"] == "404":
                    bucket.s3_client.create_bucket(Bucket=bucket.name)
                    logger.info(f"Created minio bucket {bucket.name!r}")
                else:
                    # The most comment problem is that the S3 doesn't match
                    # the AWS credentials configured.
                    # If that's the case, this will raise a 403 Forbidden
                    # ClientError.
                    raise

    @staticmethod
    def _check_mandatory_settings():
        """You *have* have set the following settings..."""
        mandatory = ("SYMBOL_URLS", "UPLOAD_DEFAULT_URL", "UPLOAD_TRY_SYMBOLS_URL")
        for key in mandatory:
            if not getattr(settings, key):
                raise ValueError(
                    f"You have to set settings.{key} "
                    f"(environment variable DJANGO_{key})"
                )

    @staticmethod
    def _check_upload_s3_url_is_download_s3_url():
        """If UPLOAD_DEFAULT_URL is not in SYMBOL_URLS it's just too
        weird. It means we'd upload to a S3 bucket we'd never read
        from and thus it'd be impossible to know the upload worked.
        """
        if settings.UPLOAD_DEFAULT_URL not in settings.SYMBOL_URLS:
            raise ValueError(
                f"The settings.UPLOAD_DEFAULT_URL "
                f"({settings.UPLOAD_DEFAULT_URL!r}) has to be one of the URLs "
                f"in settings.SYMBOL_URLS ({settings.SYMBOL_URLS!r})"
            )
