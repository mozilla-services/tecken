# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import zipfile
import gzip
import shutil
import logging
import socket

import markus
from botocore.exceptions import ClientError
from botocore.vendored.requests.exceptions import ReadTimeout

from django.conf import settings
from django.utils import timezone

from tecken.upload.models import FileUpload
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.decorators import cache_memoize


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')

downloader = SymbolDownloader(settings.SYMBOL_URLS)


class UnrecognizedArchiveFileExtension(ValueError):
    """Happens when you try to extract a file name we don't know how
    to extract."""


def dump_and_extract(root_dir, file_buffer, name):
    if name.lower().endswith('.zip'):
        zf = zipfile.ZipFile(file_buffer)
        zf.extractall(root_dir)
    else:
        raise UnrecognizedArchiveFileExtension(os.path.splitext(name)[1])
    return root_dir


class FileMember:
    # XXX switched to namedtuple or something
    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.size = os.stat(path).st_size


def get_archive_members(directory):
    # For each file in the directory return an instance of FileMember.
    # This is sugar for just returning a generator of dicts.
    for root, dirs, files in os.walk(directory):
        for name in files:
            fn = os.path.join(root, name)
            relative_name = fn[len(directory) + 1:]
            yield FileMember(fn, relative_name)


def _key_existing_size_miss(client, bucket, key):
    logger.debug(f'key_existing_size cache miss on {bucket}:{key}')


def _key_existing_size_hit(client, bucket, key):
    logger.debug(f'key_existing_size cache hit on {bucket}:{key}')


@cache_memoize(
    settings.MEMOIZE_KEY_EXISTING_SIZE_SECONDS,
    prefix='key_existing_size',
    args_rewrite=lambda client, bucket, key: (f'{bucket}:{key}',),
    miss_callable=_key_existing_size_miss,
    hit_callable=_key_existing_size_hit,
)
@metrics.timer_decorator('upload_file_exists')
def key_existing_size(client, bucket, key):
    """return the key's size if it exist, else 0"""
    # Return 0 if the key can't be found so the memoize cache can cope
    try:
        response = client.head_object(
            Bucket=bucket,
            Key=key,
        )
        return response['ContentLength']
    except ClientError as exception:
        if exception.response['Error']['Code'] == '404':
            return 0
        raise
    except (ReadTimeout, socket.timeout) as exception:
        logger.info(
            f'ReadTimeout trying to list_objects_v2 for {bucket}:'
            f'{key} ({exception})'
        )
        return 0


def should_compressed_key(key_name):
    """Return true if, based on this key name, the content should be
    gzip compressed."""
    key_extension = os.path.splitext(key_name)[1].lower()[1:]
    return key_extension in settings.COMPRESS_EXTENSIONS


def get_key_content_type(key_name):
    """Return a specific mime type this kind of key name should use, or None"""
    key_extension = os.path.splitext(key_name)[1].lower()[1:]
    return settings.MIME_OVERRIDES.get(key_extension)


@metrics.timer_decorator('upload_file_upload')
def upload_file_upload(
    s3_client,
    bucket_name,
    key_name,
    file_path,
    upload_id=None,
    microsoft_download=False,
    s3_client_lookup=None,
):
    # The reason you might want to pass a different client for
    # looking up existing sizes is because you perhaps want to use
    # a client that is configured to be a LOT less patient.
    # If there's every a ReadTimeout or ConnectionTimeout in the
    # existing size lookup, that's probably OK and worth ignoring.
    # However, when we have to look up the size of 100 different
    # files, we don't want this rather simple operation to be allowed
    # to take too long. Because if it times out, it's safe to just
    # assume the file doesn't already exist.
    existing_size = key_existing_size(
        s3_client_lookup or s3_client,
        bucket_name,
        key_name
    )

    if should_compressed_key(key_name):
        compressed = True
        with metrics.timer('upload_gzip_payload'):
            with open(file_path, 'rb') as f_in:
                with gzip.open(file_path + '.gz', 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                    # Change it from now on to this new file name
                    file_path = file_path + '.gz'
    else:
        compressed = False

    size = os.stat(file_path).st_size

    if existing_size and existing_size == size:
        # Then don't bother!
        return

    update = existing_size and existing_size != size

    file_upload = FileUpload.objects.create(
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key_name,
        update=update,
        compressed=compressed,
        size=size,
        microsoft_download=microsoft_download,
    )

    content_type = get_key_content_type(key_name)

    # boto3 will raise a botocore.exceptions.ParamValidationError
    # error if you try to do something like:
    #
    #  s3.put_object(Bucket=..., Key=..., Body=..., ContentEncoding=None)
    #
    # ...because apparently 'NoneType' is not a valid type.
    # We /could/ set it to something like '' but that feels like an
    # actual value/opinion. Better just avoid if it's not something
    # really real.
    extras = {}
    if content_type:
        extras['ContentType'] = content_type
    if compressed:
        extras['ContentEncoding'] = 'gzip'

    logger.debug('Uploading file {!r} into {!r}'.format(
        key_name,
        bucket_name,
    ))
    with metrics.timer('upload_put_object'):
        with open(file_path, 'rb') as f:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=key_name,
                Body=f,
                **extras,
            )
    FileUpload.objects.filter(id=file_upload.id).update(
        completed_at=timezone.now(),
    )
    logger.info(f'Uploaded key {key_name}')
    metrics.incr('upload_file_upload_upload', 1)

    # If we managed to upload a file, different or not,
    # cache invalidate the key_existing_size() lookup.
    try:
        key_existing_size.invalidate(s3_client, bucket_name, key_name)
    except Exception as exception:  # pragma: no cover
        if settings.DEBUG:
            raise
        logger.error(
            f'Unable to invalidate key size {key_name}',
            exc_info=True
        )

    # Take this opportunity to inform possible caches that the file,
    # if before wasn't the case, is now stored in S3.
    symbol, debugid, filename = key_name.split(
        settings.SYMBOL_FILE_PREFIX + '/'
    )[1].split('/')
    try:
        downloader.invalidate_cache(
            symbol, debugid, filename
        )
    except Exception as exception:  # pragma: no cover
        if settings.DEBUG:
            raise
        logger.error(
            f'Unable to invalidate symbol {symbol}/{debugid}/{filename}',
            exc_info=True
        )

    return file_upload
