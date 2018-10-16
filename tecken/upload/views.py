# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re
import logging
import fnmatch
import zipfile
import hashlib
import os
import time
import concurrent.futures

import requests
from botocore.exceptions import ClientError
import markus
from encore.concurrent.futures.synchronous import SynchronousExecutor
from google.api_core.exceptions import BadRequest as google_BadRequest

from django import http
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.csrf import csrf_exempt

from tecken.base.utils import filesizeformat, invalid_s3_key_name_characters
from tecken.base.decorators import (
    api_login_required,
    api_any_permission_required,
    api_require_POST,
    make_tempdir,
)
from tecken.upload.utils import (
    dump_and_extract,
    UnrecognizedArchiveFileExtension,
    DuplicateFileDifferentSize,
    upload_file_upload,
)
from tecken.symbolicate.tasks import invalidate_symbolicate_cache_task
from tecken.upload.models import Upload
from tecken.upload.tasks import update_uploads_created_task
from tecken.upload.forms import UploadByDownloadForm, UploadByDownloadRemoteError
from tecken.s3 import S3Bucket


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


_not_hex_characters = re.compile(r"[^a-f0-9]", re.I)


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
        split = file_listing.name.split("/")
        if len(split) == 3:
            # Check the symbol and the filename part of it to make sure
            # it doesn't contain any, considered, invalid S3 characters
            # when it'd become a key.
            if invalid_s3_key_name_characters(split[0] + split[2]):
                return f"Invalid character in filename {file_listing.name!r}"
            # Check that the middle part is only hex characters.
            if not _not_hex_characters.findall(split[1]):
                continue
        elif len(split) == 1:
            if file_listing.name.lower().endswith("-symbols.txt"):
                continue
        # If it didn't get "continued" above, it's an unrecognized file
        # pattern.
        return (
            "Unrecognized file pattern. Should only be <module>/<hex>/<file> "
            "or <name>-symbols.txt and nothing else."
        )


def get_bucket_info(user, try_symbols=None):
    """return an object that has 'bucket', 'endpoint_url',
    'region'.
    Only 'bucket' is mandatory in the response object.
    """

    if try_symbols is None:
        # If it wasn't explicitly passed, we need to figure this out by
        # looking at the user who uploads.
        # Namely, we're going to see if the user has the permission
        # 'upload.upload_symbols'. If the user does, it means the user intends
        # to *not* upload Try build symbols.
        # This is based on the axiom that, if the upload is made with an
        # API token, that API token can't have *both* the
        # 'upload.upload_symbols' permission *and* the
        # 'upload.upload_try_symbols' permission.
        # If the user uploads via the web the user has a choice to check
        # a checkbox that is off by default. If doing so, the user isn't
        # using an API token, so the user might have BOTH permissions.
        # Then the default falls on this NOT being a Try upload.
        try_symbols = not user.has_perm("upload.upload_symbols")

    if try_symbols:
        url = settings.UPLOAD_TRY_SYMBOLS_URL
    else:
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
                exception = settings.UPLOAD_URL_EXCEPTIONS[email_or_wildcard]
                break

    if exception:
        url = exception

    return S3Bucket(url, try_symbols=try_symbols)


def _ignore_member_file(filename):
    """Return true if the given filename (could be a filepath), should
    be completely ignored in the upload process.

    At the moment the list is "whitelist based", meaning all files are
    processed and uploaded to S3 unless it meets certain checks.
    """
    if filename.lower().endswith("-symbols.txt"):
        return True
    return False


@metrics.timer_decorator("upload_archive")
@api_require_POST
@csrf_exempt
@api_login_required
@api_any_permission_required("upload.upload_symbols", "upload.upload_try_symbols")
@make_tempdir(settings.UPLOAD_TEMPDIR_PREFIX)
def upload_archive(request, upload_dir):
    try:
        for name in request.FILES:
            upload_ = request.FILES[name]
            file_listing = dump_and_extract(upload_dir, upload_, name)
            size = upload_.size
            url = None
            redirect_urls = None
            break
        else:
            if request.POST.get("url"):
                form = UploadByDownloadForm(request.POST)
                try:
                    is_valid = form.is_valid()
                except UploadByDownloadRemoteError as exception:
                    return http.JsonResponse({"error": str(exception)}, status=500)
                if is_valid:
                    url = form.cleaned_data["url"]
                    name = form.cleaned_data["upload"]["name"]
                    size = form.cleaned_data["upload"]["size"]
                    size_fmt = filesizeformat(size)
                    logger.info(f"Download to upload {url} ({size_fmt})")
                    redirect_urls = form.cleaned_data["upload"]["redirect_urls"] or None
                    download_name = os.path.join(upload_dir, name)
                    with metrics.timer("upload_download_by_url"):
                        response_stream = requests.get(
                            url, stream=True, timeout=(5, 300)
                        )
                        with open(download_name, "wb") as f:
                            # Read 1MB at a time
                            chunk_size = 1024 * 1024
                            stream = response_stream.iter_content(chunk_size=chunk_size)
                            count_chunks = 0
                            start = time.time()
                            for chunk in stream:
                                if chunk:  # filter out keep-alive new chunks
                                    f.write(chunk)
                                count_chunks += 1
                            end = time.time()
                            total_size = chunk_size * count_chunks
                            download_speed = size / (end - start)
                            logger.info(
                                f"Read {count_chunks} chunks of "
                                f"{filesizeformat(chunk_size)} each "
                                f"totalling {filesizeformat(total_size)} "
                                f"({filesizeformat(download_speed)}/s)."
                            )
                    file_listing = dump_and_extract(upload_dir, download_name, name)
                    os.remove(download_name)
                else:
                    for key, errors in form.errors.as_data().items():
                        return http.JsonResponse(
                            {"error": errors[0].message}, status=400
                        )
            else:
                return http.JsonResponse(
                    {
                        "error": (
                            "Must be multipart form data with at " "least one file"
                        )
                    },
                    status=400,
                )
    except zipfile.BadZipfile as exception:
        return http.JsonResponse({"error": str(exception)}, status=400)
    except UnrecognizedArchiveFileExtension as exception:
        return http.JsonResponse(
            {"error": f'Unrecognized archive file extension "{exception}"'}, status=400
        )
    except DuplicateFileDifferentSize as exception:
        return http.JsonResponse({"error": str(exception)}, status=400)
    error = check_symbols_archive_file_listing(file_listing)
    if error:
        return http.JsonResponse({"error": error.strip()}, status=400)

    # If you pass an extract argument, independent of value, with key 'try'
    # then we definitely knows this is a Try symbols upload.
    is_try_upload = request.POST.get("try")

    bucket_info = get_bucket_info(request.user, try_symbols=is_try_upload)
    if is_try_upload is None:
        # If 'is_try_upload' isn't immediately true by looking at the
        # request.POST parameters, the get_bucket_info() function can
        # figure it out too.
        is_try_upload = bucket_info.try_symbols
    else:
        # In case it's passed in as a string
        is_try_upload = bool(is_try_upload)
    client = bucket_info.get_s3_client(
        read_timeout=settings.S3_PUT_READ_TIMEOUT,
        connect_timeout=settings.S3_PUT_CONNECT_TIMEOUT,
    )
    # Use a different s3 client for doing the lookups.
    # That's because we don't want the size lookup to severly accumulate
    # in the case of there being some unpredictable slowness.
    # When that happens the lookup is quickly cancelled and it assumes
    # the file does not exist.
    # See http://botocore.readthedocs.io/en/latest/reference/config.html#botocore.config.Config  # noqa
    lookup_client = bucket_info.get_s3_client(
        read_timeout=settings.S3_LOOKUP_READ_TIMEOUT,
        connect_timeout=settings.S3_LOOKUP_CONNECT_TIMEOUT,
    )
    if bucket_info.is_google_cloud_storage:
        try:
            bucket = lookup_client.get_bucket(bucket_info.name)
        except google_BadRequest as exception:
            raise ImproperlyConfigured(
                f"GCS bucket {bucket_info.name!r} can not be found. "
                f"Exception: {exception}"
            )
    else:
        bucket = None
        try:
            lookup_client.head_bucket(Bucket=bucket_info.name)
        except ClientError as exception:
            if exception.response["Error"]["Code"] == "404":
                # This warning message hopefully makes it easier to see what
                # you need to do to your configuration.
                # XXX Is this the best exception for runtime'y type of
                # bad configurations.
                raise ImproperlyConfigured(
                    "S3 bucket '{}' can not be found. "
                    "Connected with region={!r} endpoint_url={!r}".format(
                        bucket_info.name, bucket_info.region, bucket_info.endpoint_url
                    )
                )
            else:  # pragma: no cover
                raise

    # Every key has a prefix. If the S3Bucket instance has it's own prefix
    # prefix that first :)
    prefix = settings.SYMBOL_FILE_PREFIX
    if bucket_info.prefix:
        prefix = f"{bucket_info.prefix}/{prefix}"

    # Make a hash string that represents every file listing in the archive.
    # Do this by making a string first out of all files listed.

    content = "\n".join(
        "{}:{}".format(x.name, x.size)
        for x in sorted(file_listing, key=lambda x: x.name)
    )
    # The MD5 is just used to make the temporary S3 file unique in name
    # if the client uploads with the same filename in quick succession.
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:30]  # nosec

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
        redirect_urls=redirect_urls,
        content_hash=content_hash,
        try_symbols=is_try_upload,
    )

    ignored_keys = []
    skipped_keys = []

    if settings.SYNCHRONOUS_UPLOAD_FILE_UPLOAD:
        # This is only applicable when running unit tests
        thread_pool = SynchronousExecutor()
    else:
        thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.UPLOAD_FILE_UPLOAD_MAX_WORKERS or None
        )
    file_uploads_created = 0
    uploaded_symbol_keys = []
    key_to_symbol_keys = {}
    with thread_pool as executor:
        future_to_key = {}
        for member in file_listing:
            if _ignore_member_file(member.name):
                ignored_keys.append(member.name)
                continue
            key_name = os.path.join(prefix, member.name)
            # We need to know and remember, for every file attempted,
            # what that name corresponds to as a "symbol key".
            # A symbol key is, for example, ('xul.pdb', 'A7D6F1BBA7D6F1BB1')
            symbol_key = tuple(member.name.split("/")[:2])
            key_to_symbol_keys[key_name] = symbol_key
            future_to_key[
                executor.submit(
                    upload_file_upload,
                    bucket or client,
                    bucket_info.name,
                    key_name,
                    member.path,
                    upload=upload_obj,
                    s3_client_lookup=bucket or lookup_client,
                )
            ] = key_name
        # Now lets wait for them all to finish and we'll see which ones
        # were skipped and which ones were created.
        for future in concurrent.futures.as_completed(future_to_key):
            file_upload = future.result()
            if file_upload:
                file_uploads_created += 1
                uploaded_symbol_keys.append(key_to_symbol_keys[file_upload.key])
            else:
                skipped_keys.append(future_to_key[future])
                metrics.incr("upload_file_upload_skip", 1)

    if file_uploads_created:
        logger.info(f"Created {file_uploads_created} FileUpload objects")
        # If there were some file uploads, there will be some symbol keys
        # that we can send to a background task to invalidate.
        invalidate_symbolicate_cache_task.delay(uploaded_symbol_keys)
    else:
        logger.info(f"No file uploads created for {upload_obj!r}")

    Upload.objects.filter(id=upload_obj.id).update(
        skipped_keys=skipped_keys or None,
        ignored_keys=ignored_keys or None,
        completed_at=timezone.now(),
    )

    # Re-calculate the UploadsCreated for today.
    update_uploads_created_task.delay()

    metrics.incr("upload_uploads", tags=[f"try:{is_try_upload}"])

    return http.JsonResponse({"upload": _serialize_upload(upload_obj)}, status=201)


def _serialize_upload(upload):
    return {
        "id": upload.id,
        "size": upload.size,
        "filename": upload.filename,
        "bucket": upload.bucket_name,
        "region": upload.bucket_region,
        "download_url": upload.download_url,
        "try_symbols": upload.try_symbols,
        "redirect_urls": upload.redirect_urls or [],
        "completed_at": upload.completed_at,
        "created_at": upload.created_at,
        "user": upload.user.email,
        "skipped_keys": upload.skipped_keys or [],
    }
