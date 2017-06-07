# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
import logging
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from celery import shared_task

from django.conf import settings
from django.utils import timezone

from tecken.upload.models import Upload, FileUpload
from tecken.upload.utils import get_archive_members

logger = logging.getLogger('tecken')


@shared_task
def upload_inbox_upload(upload_id):
    """A zip file has been uploaded to the "inbox" folder.
    Now we need to download that, split it up into individual files
    and record this.
    The upload object should contain all necessary information for
    making a S3 connection the same way.
    """
    upload = Upload.objects.get(id=upload_id)

    options = {}
    if upload.bucket_endpoint_url:
        options['endpoint_url'] = upload.bucket_endpoint_url
    if upload.bucket_region:
        options['region_name'] = upload.bucket_region
    session = boto3.session.Session()
    s3_client = session.client('s3', **options)

    # First download the file
    buf = BytesIO()
    s3_client.download_fileobj(
        upload.bucket_name,
        upload.inbox_key,
        buf,
    )

    # buf.seek(0)  # XXX is this necessary?

    file_uploads_created = []

    for member in get_archive_members(buf, upload.filename):
        key_name = os.path.join(
            settings.UPLOAD_FILE_PREFIX, member.name
        )
        # Did we already have this exact file uploaded?
        try:
            existing_object = s3_client.head_object(
                Bucket=upload.bucket_name,
                Key=key_name,
            )
            # Only upload if the size is different.
            # So set this to None if it's already there and same size.
            if existing_object['ContentLength'] == member.size:
                # Moving on.
                continue
        except ClientError as exception:
            if exception.response['Error']['Code'] == '404':
                # It's a brand new one!
                existing_object = None
            else:
                raise

        # E.g. 'foo.sym' becomes 'sym' and 'noextension' becomes ''
        key_extension = os.path.splitext(key_name)[1].lower()[1:]
        compress = key_extension in settings.COMPRESS_EXTENSIONS

        file_buffer = BytesIO()
        if compress:
            content_encoding = 'gzip'
            # We need to read in the whole file, and compress it to a new
            # bytes object.
            with gzip.GzipFile(fileobj=file_buffer, mode='w') as f:
                f.write(member.extractor().read())
        else:
            content_encoding = None
            file_buffer.write(member.extractor().read())

        # Extract the size from the file object independent of how it
        # was created; be that by GzipFile or just member.extractor().read().
        file_buffer.seek(0, os.SEEK_END)
        size = file_buffer.tell()
        file_buffer.seek(0)

        file_upload = FileUpload(
            upload=upload,
            bucket_name=upload.bucket_name,
            key=key_name,
            update=bool(existing_object),
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
            upload.bucket_name,
        ))
        s3_client.put_object(
            Bucket=upload.bucket_name,
            Key=key_name,
            Body=file_buffer,
            **extras,
        )
        file_upload.completed_at = timezone.now()
        file_uploads_created.append(file_upload)

    if file_uploads_created:
        FileUpload.objects.bulk_create(file_uploads_created)
    else:
        logger.warning(
            'No file uploads created for {!r}'.format(
                upload,
            )
        )

    # Now we can delete the inbox file.
    s3_client.delete_object(
        Bucket=upload.bucket_name,
        Key=upload.inbox_key,
    )

    upload.refresh_from_db()
    upload.completed_at = timezone.now()
    upload.save()
