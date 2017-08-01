# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import re
import logging
import fnmatch
import hashlib
import zipfile

from botocore.exceptions import ClientError
import markus

from django import http
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from tecken.base.decorators import api_login_required, api_permission_required
from tecken.upload.utils import get_archive_members
from tecken.upload.models import Upload, FileUpload
from tecken.upload.tasks import upload_inbox_upload
from tecken.s3 import S3Bucket


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


_not_hex_characters = re.compile(r'[^a-f0-9]', re.I)


def check_symbols_archive_file_listing(file_listings):
    """return a string (the error) if there was something not as expected"""
    for file_listing in file_listings:
        for snippet in settings.DISALLOWED_SYMBOLS_SNIPPETS:
            if snippet in file_listing.name:
                return (
                    "Content of archive file contains the snippet "
                    "'%s' which is not allowed\n" % snippet
                )
        # Now check that the filename is matching according to these rules:
        # 1. Either /<name1>/hex/<name2>,
        # 2. Or, /<name>-symbols.txt
        # Anything else should be considered and unrecognized file pattern
        # and thus rejected.
        split = file_listing.name.split('/')
        if len(split) == 3:
            # check that the middle part is only hex characters
            if not _not_hex_characters.findall(split[1]):
                continue
        elif len(split) == 1:
            if file_listing.name.lower().endswith('-symbols.txt'):
                continue
        # If it didn't get "continued" above, it's an unrecognized file
        # pattern.
        return (
            'Unrecognized file pattern. Should only be <module>/<hex>/<file> '
            'or <name>-symbols.txt and nothing else.'
        )


def get_bucket_info(user):
    """return an object that has 'bucket', 'endpoint_url',
    'region'.
    Only 'bucket' is mandatory in the response object.
    """
    url = settings.UPLOAD_DEFAULT_URL
    exceptions = settings.UPLOAD_URL_EXCEPTIONS
    if user.email.lower() in exceptions:
        # easy
        exception = exceptions[user.email.lower()]
    else:
        # match against every possible wildcard
        exception = None  # assume no match
        for email_or_wildcard in settings.UPLOAD_URL_EXCEPTIONS:
            if fnmatch.fnmatch(user.email.lower(), email_or_wildcard.lower()):
                # a match!
                exception = settings.UPLOAD_URL_EXCEPTIONS[
                    email_or_wildcard
                ]
                break

    if exception:
        url = exception

    return S3Bucket(url)


@metrics.timer_decorator('upload_archive')
@require_POST
@csrf_exempt
@api_login_required
@api_permission_required('upload.upload_symbols')
@transaction.atomic
def upload_archive(request):
    for name in request.FILES:
        upload = request.FILES[name]
        size = upload.size
        break
    else:
        # XXX Make this a JSON BadRequest
        return http.HttpResponseBadRequest(
            "Must be multipart form data with at least one file"
        )
    if not size:
        # XXX Make this a JSON BadRequest
        return http.HttpResponseBadRequest('File size 0')

    try:
        file_listing = list(get_archive_members(upload, name))
    except zipfile.BadZipfile as exception:
        # XXX Make this a JSON BadRequest
        return http.HttpResponseBadRequest(exception)
    error = check_symbols_archive_file_listing(file_listing)
    if error:
        # XXX Make this a JSON BadRequest
        return http.HttpResponseBadRequest(error)

    # Upload the archive file into the "inbox".
    # This is a folder in the root of the bucket where the upload
    # belongs.
    bucket_info = get_bucket_info(request.user)
    try:
        bucket_info.s3_client.head_bucket(Bucket=bucket_info.name)
    except ClientError as exception:
        if exception.response['Error']['Code'] == '404':
            # This warning message hopefully makes it easier to see what
            # you need to do to your configuration.
            # XXX Is this the best exception for runtime'y type of
            # bad configurations.
            raise ImproperlyConfigured(
                "S3 bucket '{}' can not be found. "
                'Connected with region={!r} endpoint_url={!r}'.format(
                    bucket_info.name,
                    bucket_info.region,
                    bucket_info.endpoint_url,
                )
            )
        else:  # pragma: no cover
            raise
    # Turn the file listing into a string to turn it into a hash
    content = '\n'.join(
        '{}:{}'.format(x.name, x.size) for x in file_listing
    )
    # The MD5 is just used to make the temporary S3 file unique in name
    # if the client uploads with the same filename in quick succession.
    content_hash = hashlib.md5(
        content.encode('utf-8')
    ).hexdigest()[:12]  # nosec
    key = 'inbox/{date}/{content_hash}/{name}'.format(
        date=timezone.now().strftime('%Y-%m-%d'),
        content_hash=content_hash,
        name=name,
    )
    # Record that we made this upload
    upload_obj = Upload.objects.create(
        user=request.user,
        filename=name,
        inbox_key=key,
        bucket_name=bucket_info.name,
        bucket_region=bucket_info.region,
        bucket_endpoint_url=bucket_info.endpoint_url,
        size=size,
    )
    with metrics.timer('upload_to_inbox'):
        upload.seek(0)
        bucket_info.s3_client.put_object(
            Bucket=bucket_info.name,
            Key=key,
            Body=upload,
        )

    upload_inbox_upload.delay(upload_obj.pk)

    # Take the opportunity to also try to clear out old uploads that
    # have gotten stuck and still hasn't moved for some reason.
    # Note! This might be better to do with a cron job some day. But that
    # requires a management command that can be run in production.
    incomplete_uploads = Upload.objects.filter(
        completed_at__isnull=True,
        created_at__lt=(
            timezone.now() - datetime.timedelta(
                seconds=settings.UPLOAD_REATTEMPT_LIMIT_SECONDS
            )
        ),
        attempts__lt=settings.UPLOAD_REATTEMPT_LIMIT_TIMES
    )
    for old_upload_obj in incomplete_uploads.order_by('created_at'):
        cache_key = f'reattempt:{old_upload_obj.id}'
        if not cache.get(cache_key):
            logger.info(
                f'Reattempting incomplete upload from {old_upload_obj!r}'
            )
            upload_inbox_upload.delay(old_upload_obj.id)
            cache.set(
                cache_key,
                True,
                settings.UPLOAD_REATTEMPT_LIMIT_SECONDS
            )

    return http.JsonResponse(
        {'upload': _serialize_upload(upload_obj)},
        status=201,
    )


def _serialize_upload(upload, flat=False):
    serialized = {
        'id': upload.id,
        'size': upload.size,
        'filename': upload.filename,
        'bucket': upload.bucket_name,
        'region': upload.bucket_region,
        'completed_at': upload.completed_at,
        'created_at': upload.created_at,
        'user': upload.user.email,
        'skipped_keys': upload.skipped_keys or [],
    }
    if not flat:
        serialized['files'] = []
        for file_upload in FileUpload.objects.filter(upload=upload):
            serialized['files'].append({
                'bucket': file_upload.bucket_name,
                'key': file_upload.key,
                'update': file_upload.update,
                'compressed': file_upload.compressed,
                'size': file_upload.size,
                'completed_at': file_upload.completed_at,
                'created_at': file_upload.created_at,
            })
    return serialized
