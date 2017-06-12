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
from django.shortcuts import get_object_or_404
from django.core.urlresolvers import reverse

from tecken.base.decorators import api_login_required, api_permission_required
from tecken.upload.utils import preview_archive_content
from tecken.upload.models import Upload, FileUpload
from tecken.upload.tasks import upload_inbox_upload
from tecken.s3 import S3Bucket
from .forms import SearchForm


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


@api_login_required
@api_permission_required('upload.add_upload')
def search(request):
    """Return a JSON search result. If no parameters are sent, cap
    to the top XXX number of uploads.
    The results are always sorted by creation date descending.
    """
    context = {
        'uploads': [],
    }
    # XXX add pagination
    qs = Upload.objects.all().order_by('-created_at')
    form = SearchForm(request.GET)
    if not form.is_valid():
        # XXX Make this a JSON BadRequest
        return http.HttpResponseBadRequest(str(form.errors))

    if form.cleaned_data['start_date']:
        qs = qs.filter(created_at__gte=form.cleaned_data['start_date'])
    if form.cleaned_data['end_date']:
        qs = qs.filter(created_at__lt=form.cleaned_data['end_date'])
    if form.cleaned_data['user']:
        if form.cleaned_data['user'].isdigit():
            qs = qs.filter(user_id=int(form.cleaned_data['user']))
        else:
            qs = qs.filter(user__email__icontains=form.cleaned_data['user'])

    for upload in qs.select_related('user'):
        serialized = _serialize_upload(upload, flat=True)
        serialized['url'] = request.build_absolute_uri(
            reverse('upload:upload', args=(upload.id,))
        )
        context['uploads'].append(serialized)
    return http.JsonResponse(context)


@api_login_required
@api_permission_required('upload.add_upload')
def upload(request, id):
    """Return all the information about one upload or 404.
    """
    upload = get_object_or_404(Upload, id=id)
    context = {
        'upload': _serialize_upload(upload),
    }
    return http.JsonResponse(context)
