# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
import logging
from io import BytesIO

import markus
from botocore.exceptions import (
    EndpointConnectionError,
    ConnectionError,
    ClientError,
)
from celery import shared_task
# from celery.exceptions import SoftTimeLimitExceeded

from django.conf import settings
from django.utils import timezone

from tecken.upload.models import Upload, FileUpload
from tecken.upload.utils import get_archive_members
from tecken.s3 import get_s3_client
from tecken.base.symboldownloader import SymbolDownloader
from tecken.boto_extra import (
    reraise_clienterrors,
    reraise_endpointconnectionerrors
)

logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')

downloader = SymbolDownloader(settings.SYMBOL_URLS)


@shared_task(autoretry_for=(
    EndpointConnectionError,
    ConnectionError,
    ClientError,
))
@reraise_clienterrors
@reraise_endpointconnectionerrors
def upload_inbox_upload(upload_id):
    """A zip file has been uploaded to the "inbox" folder.
    Now we need to download that, split it up into individual files
    and record this.
    The upload object should contain all necessary information for
    making a S3 connection the same way.

    See https://github.com/boto/boto3/issues/1128
    When running this, we see one "Starting new HTTPS connection"
    for each file in the zip.
    """
    try:
        upload = Upload.objects.get(id=upload_id)
    except Upload.DoesNotExist:
        print(f"FAILED TO FIND {upload_id}")
        recent_uploads = Upload.objects.all().order_by('-created')[:5]
        for up in recent_uploads:
            print(f'\t{up.id}\t{up.created}')
        raise

    # Immediately persist that we are about to attempt to process this upload.
    # The reason for doing this here rather than at the end when
    # we call the .save() is that errors could happen in between.
    upload.attempts += 1
    upload.save()

    s3_client = get_s3_client(
        endpoint_url=upload.bucket_endpoint_url,
        region_name=upload.bucket_region,
    )

    # First download the file
    buf = BytesIO()
    if upload.inbox_filepath:
        logger.debug(
            'Upload task tries to read {upload.inbox_filepath}'
        )
        with open(upload.inbox_filepath, 'rb') as f:
            buf.write(f.read())
    else:
        s3_client.download_fileobj(
            upload.bucket_name,
            upload.inbox_key,
            buf,
        )

    file_uploads_created = []
    previous_uploads = FileUpload.objects.filter(
        upload=upload,
        completed_at__isnull=False,
    )
    previous_uploads_keys = [x.key for x in previous_uploads.only('key')]
    skipped_keys = []
    ignored_keys = []
    save_upload_now = False
    try:
        for member in get_archive_members(buf, upload.filename):
            if _ignore_member_file(member.name):
                ignored_keys.append(member.name)
                continue
            # XXX consider a metrics timer function here
            file_upload, key_name = create_file_upload(
                s3_client,
                upload,
                member,
                previous_uploads_keys,
            )
            # The _create_file_upload() function might return None
            # which means it decided there is no need to make an upload
            # of this specific file.
            if file_upload:
                logger.info(f'Uploaded key {key_name}')
                file_uploads_created.append(file_upload)
                metrics.incr('upload_file_upload_upload', 1)
            elif key_name not in previous_uploads_keys:
                logger.info(f'Skipped key {key_name}')
                skipped_keys.append(key_name)
                metrics.incr('upload_file_upload_skip', 1)
    except Exception:
        save_upload_now = True
        raise
    finally:
        # Since we're using a bulk insert approach (since it's more
        # efficient to bulk insert a bunch), if something ever goes wrong
        # during the loop, we should at least log that the ones that *did*
        # work are properly recorded. That means, when this whole task
        # celery-retries it can continue based on what's already been
        # uploaded.
        if file_uploads_created:
            FileUpload.objects.bulk_create(file_uploads_created)
        else:
            logger.info(
                'No file uploads created for {!r}'.format(
                    upload,
                )
            )

        # We also want to log any skipped keys
        skipped_keys_set = set(skipped_keys)
        skipped_keys_set.update(set(upload.skipped_keys or []))
        # And the ignored keys
        ignored_keys_set = set(ignored_keys)
        ignored_keys_set.update(set(upload.ignored_keys or []))
        if save_upload_now:
            # If an exception has happened, before we let the exception
            # raise, we want to record which ones we skipped
            upload.refresh_from_db()
            upload.skipped_keys = skipped_keys or None
            upload.ignored_keys = ignored_keys or None
            upload.save()

    # Now we can delete the inbox file.
    if upload.inbox_filepath:
        os.remove(upload.inbox_filepath)
        _delete_empty_directories(
            os.path.dirname(upload.inbox_filepath),
            settings.UPLOAD_INBOX_DIRECTORY,
        )
    else:
        s3_client.delete_object(
            Bucket=upload.bucket_name,
            Key=upload.inbox_key,
        )

    upload.refresh_from_db()
    upload.completed_at = timezone.now()
    upload.skipped_keys = skipped_keys or None
    upload.ignored_keys = ignored_keys or None
    upload.save()


def _delete_empty_directories(directory, max_parent):
    """Given a directory, delete it if it's empty. Also, delete the parent
    directory (recursively) if that's empty too."""
    max_parent = os.path.abspath(max_parent)
    if not os.listdir(directory):
        os.rmdir(directory)
        parent = os.path.abspath(os.path.join(directory, '..'))
        if parent != max_parent:
            _delete_empty_directories(parent, max_parent)


def _ignore_member_file(filename):
    """Return true if the given filename (could be a filepath), should
    be completely ignored in the upload process.

    At the moment the list is "whitelist based", meaning all files are
    processed and uploaded to S3 unless it meets certain checks.
    """
    if filename.lower().endswith('-symbols.txt'):
        return True
    return False


def _key_existing_size(client, bucket, key):
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


@metrics.timer_decorator('upload_create_file_upload')
def create_file_upload(s3_client, upload, member, previous_uploads_keys):
    """Actually do the S3 PUT of an individual file (member of an archive).
    Returns a tuple of (FileUpload instance, key name). If we decide to
    NOT upload the file, we return (None, key name).
    """
    key_name = os.path.join(
        settings.SYMBOL_FILE_PREFIX, member.name
    )
    if key_name in previous_uploads_keys:
        # If this upload is a retry, the upload object might already have
        # some previous *file* uploads in it. If that's the case, we
        # don't need to even consider this file again.
        logger.debug(f'{key_name!r} already uploaded. Skipping')
        return None, key_name

    return upload_file_upload(
        s3_client,
        upload.bucket_name,
        key_name,
        member.extractor().read(),
        upload=upload,
    ), key_name


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
    size_in_s3 = _key_existing_size(s3_client, bucket_name, key_name)
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
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key_name,
        Body=file_buffer,
        **extras,
    )
    file_upload.completed_at = timezone.now()

    # Take this opportunity to inform possible caches that the file,
    # if before wasn't the case, is now stored in S3.
    symbol, debugid, filename = _key_name_to_parts(key_name)
    try:
        downloader.invalidate_cache(
            symbol, debugid, filename
        )
    except Exception as exception:  # pragma: no cover
        if 1 or settings.DEBUG:
            raise
        logger.error(
            f'Unable to invalidate symbol {symbol}/{debugid}/{filename}',
            exc_info=True
        )

    return file_upload


def _key_name_to_parts(key_name):
    return key_name.split(settings.SYMBOL_FILE_PREFIX + '/')[1].split('/')
