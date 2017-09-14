# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os

from botocore.exceptions import ClientError, EndpointConnectionError

from django.core import checks
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from dockerflow.django.checks import (
    ERROR_CANNOT_CONNECT_REDIS,
    ERROR_MISSING_REDIS_CLIENT,
    ERROR_MISCONFIGURED_REDIS,
    ERROR_REDIS_PING_FAILED
)
from tecken.s3 import S3Bucket


def check_redis_store_connected(app_configs, **kwargs):
    """
    This code is copied from the dockerflow.django.checks but with a
    different name of the connection.
    """
    import redis
    from django_redis import get_redis_connection
    errors = []

    try:
        # Note! This name 'store' is specific only to tecken
        connection = get_redis_connection('store')
    except redis.ConnectionError as e:
        msg = 'Could not connect to redis: {!s}'.format(e)
        errors.append(checks.Error(msg, id=ERROR_CANNOT_CONNECT_REDIS))
    except NotImplementedError as e:
        msg = 'Redis client not available: {!s}'.format(e)
        errors.append(checks.Error(msg, id=ERROR_MISSING_REDIS_CLIENT))
    except ImproperlyConfigured as e:
        msg = 'Redis misconfigured: "{!s}"'.format(e)
        errors.append(checks.Error(msg, id=ERROR_MISCONFIGURED_REDIS))
    else:
        result = connection.ping()
        if not result:
            msg = 'Redis ping failed'
            errors.append(checks.Error(msg, id=ERROR_REDIS_PING_FAILED))
    return errors


def check_s3_urls(app_configs, **kwargs):
    errors = []
    checked = []

    def check_url(url, setting_key):
        if url in checked:
            return
        bucket = S3Bucket(url)
        if not bucket.private:
            return
        try:
            bucket.s3_client.head_bucket(Bucket=bucket.name)
        except ClientError as exception:
            if exception.response['Error']['Code'] in ('403', '404'):
                errors.append(checks.Error(
                    f'Unable to connect to {url} (bucket={bucket.name!r}, '
                    f'found in settings.{setting_key}) due to '
                    f'ClientError ({exception.response!r})',
                    id='tecken.health.E002'
                ))
            else:
                raise
        except EndpointConnectionError:
            errors.append(checks.Error(
                f'Unable to connect to {url} (bucket={bucket.name!r}, '
                f'found in settings.{setting_key}) due to '
                f'EndpointConnectionError',
                id='tecken.health.E001'
            ))
        else:
            checked.append(url)

    for url in settings.SYMBOL_URLS:
        check_url(url, 'SYMBOL_URLS')
    for url in settings.UPLOAD_URL_EXCEPTIONS.values():
        check_url(url, 'UPLOAD_URL_EXCEPTIONS')

    return errors


def check_upload_inbox_directory(app_configs, **kwargs):
    """
    If the settings.UPLOAD_INBOX_DIRECTORY is set, the directory needs to
    exist and if it already exists, check that we can write to it.
    """
    errors = []
    if settings.UPLOAD_INBOX_DIRECTORY:
        directory = os.path.abspath(settings.UPLOAD_INBOX_DIRECTORY)
        if not os.path.isdir(directory):
            # Then the test is that we need to be able to create it!
            try:
                os.makedirs(directory)
            except OSError as exception:  # pragma: no cover
                msg = (
                    f'Unable to create UPLOAD_INBOX_DIRECTORY directory '
                    f'{directory} '
                    f'({exception.__class__.__name__}: {exception})'
                )
                errors.append(checks.Error(msg, id='tecken.health.E004'))
        else:
            # Then the test is to see if we can create a file within it.
            try:
                fp = os.path.join(directory, 'testfile.txt')
                with open(fp, 'w') as f:
                    f.write('Works\n')
                os.remove(fp)
            except OSError as exception:  # pragma: no cover
                msg = (
                    f'Unable to create a test file in the '
                    'UPLOAD_INBOX_DIRECTORY directory {directory} '
                    f'({exception.__class__.__name__}: {exception})'
                )
                errors.append(checks.Error(msg, id='tecken.health.E005'))
    return errors
