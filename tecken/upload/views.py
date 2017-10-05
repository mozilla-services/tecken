# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re
import logging
import io
import fnmatch
import zipfile
import os

import requests
from botocore.exceptions import ClientError
import markus

from django import http
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.csrf import csrf_exempt

from tecken.base.utils import filesizeformat
from tecken.base.decorators import (
    api_login_required,
    api_permission_required,
    api_require_POST
)
from tecken.upload.utils import (
    get_archive_members,
    UnrecognizedArchiveFileExtension,
    upload_file_upload,
)
from tecken.upload.models import Upload
from tecken.upload.forms import UploadByDownloadForm
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
                    f"Content of archive file contains the snippet "
                    f"'{snippet}' which is not allowed"
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
@api_require_POST
@csrf_exempt
@api_login_required
@api_permission_required('upload.upload_symbols')
def upload_archive(request):
    for name in request.FILES:
        upload = request.FILES[name]
        size = upload.size
        url = None
        break
    else:
        if request.POST.get('url'):
            form = UploadByDownloadForm(request.POST)
            if form.is_valid():
                url = form.cleaned_data['url']
                name = form.cleaned_data['upload']['name']
                size = form.cleaned_data['upload']['size']
                size_fmt = filesizeformat(size)
                logger.info(
                    f'Download to upload {url} ({size_fmt})'
                )
                upload = io.BytesIO(requests.get(url).content)
            else:
                for key, errors in form.errors.as_data().items():
                    return http.JsonResponse(
                        {'error': errors[0].message},
                        status=400,
                    )
        else:
            return http.JsonResponse(
                {
                    'error': (
                        'Must be multipart form data with at least one file'
                    )
                },
                status=400,
            )
    if not size:
        return http.JsonResponse(
            {'error': 'File size 0'},
            status=400
        )

    try:
        file_listing = list(get_archive_members(upload, name))
    except zipfile.BadZipfile as exception:
        return http.JsonResponse(
            {'error': str(exception)},
            status=400,
        )
    except UnrecognizedArchiveFileExtension as exception:
        return http.JsonResponse(
            {'error': f'Unrecognized archive file extension "{exception}"'},
            status=400,
        )
    error = check_symbols_archive_file_listing(file_listing)
    if error:
        return http.JsonResponse({'error': error.strip()}, status=400)

    bucket_info = get_bucket_info(request.user)
    client = bucket_info.s3_client
    try:
        client.head_bucket(Bucket=bucket_info.name)
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

    def _ignore_member_file(filename):
        """Return true if the given filename (could be a filepath), should
        be completely ignored in the upload process.

        At the moment the list is "whitelist based", meaning all files are
        processed and uploaded to S3 unless it meets certain checks.
        """
        if filename.lower().endswith('-symbols.txt'):
            return True
        return False

    # Always create the Upload object no matter what happens next.
    # If all individual file uploads work out, we say this is complete.
    upload_obj = Upload.objects.create(
        user=request.user,
        filename=name,
        bucket_name=bucket_info.name,
        bucket_region=bucket_info.region,
        bucket_endpoint_url=bucket_info.endpoint_url,
        size=size,
        download_url=url,
    )

    ignored_keys = []
    skipped_keys = []
    file_uploads_created = []
    for member in get_archive_members(upload, name):
        if _ignore_member_file(member.name):
            ignored_keys.append(member.name)
            continue

        key_name = os.path.join(
            settings.SYMBOL_FILE_PREFIX, member.name
        )

        file_upload = upload_file_upload(
            client,
            bucket_info.name,
            key_name,
            member.extractor().read(),
            upload=upload_obj,
        )
        # If upload_file_upload() returns None, it means it deemed it
        # not necessary to upload this file.
        if file_upload:
            logger.info(f'Uploaded key {key_name}')
            file_uploads_created.append(file_upload)
            metrics.incr('upload_file_upload_upload', 1)
        else:
            logger.info(f'Skipped key {key_name}')
            skipped_keys.append(key_name)
            metrics.incr('upload_file_upload_skip', 1)

    if file_uploads_created:
        logger.info(f'Created {len(file_uploads_created)} FileUpload objects')
    else:
        logger.info(f'No file uploads created for {upload_obj!r}')

    Upload.objects.filter(id=upload_obj.id).update(
        completed_at=timezone.now(),
        skipped_keys=skipped_keys or None,
        ignored_keys=ignored_keys or None,
    )

    return http.JsonResponse(
        {'upload': _serialize_upload(upload_obj)},
        status=201,
    )


def _serialize_upload(upload):
    return {
        'id': upload.id,
        'size': upload.size,
        'filename': upload.filename,
        'bucket': upload.bucket_name,
        'region': upload.bucket_region,
        'download_url': upload.download_url,
        'completed_at': upload.completed_at,
        'created_at': upload.created_at,
        'user': upload.user.email,
        'skipped_keys': upload.skipped_keys or [],
    }
