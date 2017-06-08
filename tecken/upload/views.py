# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import fnmatch
import hashlib

from botocore.exceptions import ClientError
import markus

from django import http
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.csrf import csrf_exempt

from tecken.base.decorators import api_login_required, api_permission_required
from tecken.upload.utils import preview_archive_content
from tecken.upload.models import Upload
from tecken.upload.tasks import upload_inbox_upload
from tecken.s3 import S3Bucket


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


def check_symbols_archive_content(content):
    """return an error if there was something wrong"""
    for line in content.splitlines():
        for snippet in settings.DISALLOWED_SYMBOLS_SNIPPETS:
            if snippet in line:
                return (
                    "Content of archive file contains the snippet "
                    "'%s' which is not allowed\n" % snippet
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
@api_permission_required('upload.add_upload')
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

    content = preview_archive_content(upload, name)
    error = check_symbols_archive_content(content)
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
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:12]
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

    return http.HttpResponse('Created', status=201)
