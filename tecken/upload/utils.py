# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import zipfile
import gzip
import tarfile
import logging
from io import BytesIO

import markus

from django.conf import settings
from django.utils import timezone

from tecken.upload.models import FileUpload
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.decorators import cache_memoize


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')

downloader = SymbolDownloader(settings.SYMBOL_URLS)


class UnrecognizedArchiveFileExtension(ValueError):
    pass


class _ZipMember:

    def __init__(self, member, container):
        self.member = member
        self.container = container

    def extractor(self):
        return self.container.open(self.name)

    @property
    def name(self):
        return self.member.filename

    @property
    def size(self):
        return self.member.file_size


class _TarMember:

    def __init__(self, member, container):
        self.member = member
        self.container = container

    def extractor(self):
        return self.container.extractfile(self.member)

    @property
    def name(self):
        return self.member.name

    @property
    def size(self):
        return self.member.size


def get_archive_members(file_object, file_name):
    file_name = file_name.lower()
    if file_name.endswith('.zip'):
        zf = zipfile.ZipFile(file_object)
        for member in zf.infolist():
            yield _ZipMember(
                member,
                zf
            )

    elif file_name.endswith('.tar.gz') or file_name.endswith('.tgz'):
        tar = gzip.GzipFile(fileobj=file_object)
        zf = tarfile.TarFile(fileobj=tar)
        for member in zf.getmembers():
            if member.isfile():
                yield _TarMember(
                    member,
                    zf
                )

    elif file_name.endswith('.tar'):
        zf = tarfile.TarFile(fileobj=file_object)
        for member in zf.getmembers():
            # Sometimes when you make a tar file you get a
            # smaller index file copy that start with "./._".
            if member.isfile() and not member.name.startswith('./._'):
                yield _TarMember(
                    member,
                    zf
                )

    else:
        raise UnrecognizedArchiveFileExtension(os.path.splitext(file_name)[1])


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
    """return the key's size if it exist, else None.

    See
    https://www.peterbe.com/plog/fastest-way-to-find-out-if-a-file-exists-in-s3
    for why this is the better approach.
    """
    response = client.list_objects_v2(
        Bucket=bucket,
        Prefix=key,
    )
    for obj in response.get('Contents', []):
        if obj['Key'] == key:
            return obj['Size']

    # Because returning None causes problems for the cache decorator
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
    payload,
    upload_id=None,
    microsoft_download=False,
):
    existing_size = key_existing_size(s3_client, bucket_name, key_name)

    if should_compressed_key(key_name):
        compressed = True
        with metrics.timer('upload_gzip_payload'):
            file_buffer = BytesIO()
            with gzip.GzipFile(fileobj=file_buffer, mode='w') as f:
                f.write(payload)
            file_buffer.seek(0, os.SEEK_END)
            size = file_buffer.tell()
            file_buffer.seek(0)
    else:
        compressed = False
        size = len(payload)
        # This is a smart hack. The boto3 client.put_object() function
        # can either take a blob of bytes or a file-like object.
        # When we gzip the file, we need to have make it a file-like object
        # so that GzipFile creates the necessary headers.
        file_buffer = payload

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
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key_name,
            Body=file_buffer,
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
