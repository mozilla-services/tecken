# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
import logging
from io import BytesIO
from functools import wraps

from botocore.exceptions import ClientError, EndpointConnectionError
from celery import shared_task

from django.conf import settings
from django.utils import timezone

from tecken.upload.models import Upload, FileUpload
from tecken.upload.utils import get_archive_members
from tecken.s3 import get_s3_client


logger = logging.getLogger('tecken')


class OwnEndpointConnectionError(EndpointConnectionError):
    """Because the botocore.exceptions.EndpointConnectionError can't be
    pickled, if this exception happens during task work, celery
    won't be able to pickle it. So we write our own.

    See https://github.com/boto/botocore/pull/1191 for a similar problem
    with the ClientError exception.
    """

    def __init__(self, msg=None, **kwargs):
        if not msg:
            msg = self.fmt.format(**kwargs)
        Exception.__init__(self, msg)
        self.kwargs = kwargs
        self.msg = msg

    def __reduce__(self):
        return (self.__class__, (self.msg,), {'kwargs': self.kwargs})


def reraise_endpointconnectionerrors(f):
    """Decorator whose whole job is to re-raise any EndpointConnectionError
    exceptions raised to be OwnEndpointConnectionError because those
    exceptions are "better". In other words, if, instead an
    OwnEndpointConnectionError exception is raised by the task
    celery can then pickle the error. And if it can pickle the error
    it can apply its 'autoretry_for' magic.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except EndpointConnectionError as exception:
            raise OwnEndpointConnectionError(**exception.kwargs)
    return wrapper


# We currently have only this one exception in the autoretry_for parameter.
# Perhaps other types of exceptions can occur. Such as botocore.exceptions.
# ClientError or botocore.exceptions.ConnectionError (which is an alias
# for botocore.vendored.requests.exceptions.ConnectionError by the way).
# It's not clear at all when those kinds of errors happen and whether they
# can be pickled or not.
# If they do happen, add to this 'autoretry_for' parameter tuple. If,
# when they happen, cause that dreaded 'billiard.pool.MaybeEncodingError'
# error, then apply the same work that was done to OwnEndpointConnectionError.
@shared_task(autoretry_for=(OwnEndpointConnectionError,))
@reraise_endpointconnectionerrors
def upload_inbox_upload(upload_id):
    """A zip file has been uploaded to the "inbox" folder.
    Now we need to download that, split it up into individual files
    and record this.
    The upload object should contain all necessary information for
    making a S3 connection the same way.
    """
    upload = Upload.objects.get(id=upload_id)

    s3_client = get_s3_client(
        endpoint_url=upload.bucket_endpoint_url,
        region_name=upload.bucket_region,
    )

    # First download the file
    buf = BytesIO()
    s3_client.download_fileobj(
        upload.bucket_name,
        upload.inbox_key,
        buf,
    )

    # buf.seek(0)  # XXX is this necessary?

    file_uploads_created = []
    previous_uploads = FileUpload.objects.filter(
        upload=upload,
        completed_at__isnull=False,
    )
    previous_uploads_keys = [x.key for x in previous_uploads.only('key')]

    try:
        for member in get_archive_members(buf, upload.filename):
            file_upload = create_file_upload(
                s3_client,
                upload,
                member,
                previous_uploads_keys,
            )
            # The _create_file_upload() function might return None
            # which means it decided there is no need to make an upload
            # of this specific file.
            if file_upload:
                file_uploads_created.append(file_upload)

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


def create_file_upload(s3_client, upload, member, previous_uploads_keys):
    """Actually do the S3 PUT of an individual file (member of an archive).
    Returns an unsaved FileUpload instance iff the S3 put_object worked.
    """
    key_name = os.path.join(
        settings.UPLOAD_FILE_PREFIX, member.name
    )
    if key_name in previous_uploads_keys:
        # If this upload is a retry, the upload object might already have
        # some previous *file* uploads in it. If that's the case, we
        # don't need to even consider this file again.
        return

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
            return
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
    return file_upload
