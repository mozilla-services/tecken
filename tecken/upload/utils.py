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


def upload_file_upload(s3_client, bucket_name, key_name, content, upload=None):
    # E.g. 'foo.sym' becomes 'sym' and 'noextension' becomes ''
    key_extension = os.path.splitext(key_name)[1].lower()[1:]
    compress = key_extension in settings.COMPRESS_EXTENSIONS

    # Assume we're not setting a custom encoding
    content_encoding = None
    # Read the member into memory
    file_buffer = BytesIO()
    # If the file needs to be compressed, we need to do that now
    # already. Otherwise we won't be able to compare this file's size
    # with what was previously uploaded.
    if compress:
        content_encoding = 'gzip'
        file_buffer = BytesIO()
        # We need to read in the whole file, and compress it to a new
        # bytes object.
        with gzip.GzipFile(fileobj=file_buffer, mode='w') as f:
            f.write(content)
    else:
        file_buffer.write(content)

    # Extract the size from the file object independent of how it
    # was created; be that by GzipFile or just member.extractor().read().
    file_buffer.seek(0, os.SEEK_END)
    size = file_buffer.tell()
    file_buffer.seek(0)

    # Did we already have this exact file uploaded?
    size_in_s3 = key_existing_size(s3_client, bucket_name, key_name)
    if size_in_s3 is not None:
        # Only upload if the size is different.
        # So set this to None if it's already there and same size.
        if size_in_s3 == size:
            # Moving on.
            logger.debug(
                f'{key_name!r} ({bucket_name}) has not changed '
                'size. Skipping.'
            )
            return

    file_upload = FileUpload(
        upload=upload,
        bucket_name=bucket_name,
        key=key_name,
        update=size_in_s3 is not None,
        compressed=compress,
        size=size,
    )

    content_type = settings.MIME_OVERRIDES.get(key_extension)

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
    if content_encoding:
        extras['ContentEncoding'] = content_encoding

    logger.debug('Uploading file {!r} into {!r}'.format(
        key_name,
        bucket_name,
    ))
    with metrics.timer('upload_file_upload'):
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key_name,
            Body=file_buffer,
            **extras,
        )
    file_upload.completed_at = timezone.now()

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
