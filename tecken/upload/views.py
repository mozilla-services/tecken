# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import concurrent.futures
from functools import wraps
import hashlib
import logging
import os
import re
from tempfile import TemporaryDirectory
import time
import zipfile

from django import http
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from tecken.base.decorators import (
    api_login_required,
    api_any_permission_required,
    api_require_POST,
)
from tecken.base.symbolstorage import symbol_storage
from tecken.base.utils import filesizeformat, invalid_key_name_characters
from tecken.upload import executor
from tecken.upload.forms import UploadByDownloadForm, UploadByDownloadRemoteError
from tecken.upload.models import Upload
from tecken.upload.utils import (
    dump_and_extract,
    UnrecognizedArchiveFileExtension,
    DuplicateFileDifferentSize,
    upload_file_upload,
)
from tecken.librequests import session_with_retries
from tecken.libmarkus import METRICS


logger = logging.getLogger("tecken")


_not_hex_characters = re.compile(r"[^a-f0-9]", re.I)

# This list of filenames is used to validate a zip and also when iterating
# over the extracted zip.
# The names of files in this list are considered harmless and something that
# can simply be ignored.
_ignorable_filenames = (".DS_Store",)


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
        if split[-1] in _ignorable_filenames:
            continue
        if len(split) == 3:
            # Check the symbol and the filename part of it to make sure
            # it doesn't contain any, considered, invalid S3 characters
            # when it'd become a key.
            if invalid_key_name_characters(split[0] + split[2]):
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
            "or <name>-symbols.txt and nothing else. "
            f"(First unrecognized pattern was {file_listing.name})"
        )


def _ignore_member_file(filename):
    """Return true if the given filename (could be a filepath), should
    be completely ignored in the upload process.

    At the moment the list is "allow-list based", meaning all files are
    processed and uploaded to S3 unless it meets certain checks.
    """
    if filename.lower().endswith("-symbols.txt"):
        return True
    if os.path.basename(filename) in _ignorable_filenames:
        return True
    return False


def make_tempdir(tempdir_root, suffix=None):
    """Creates a temporary directory and adds to the decorated function arguments

    If the tempoarary directory root has not been created, it is created. The temporary
    directory is deleted after the function has completed.

    Usage::

        @make_tempdir(tempdir_root="/tmp")
        def some_function(arg1, arg2, tempdir, kwargs1='one'):
            assert os.path.isdir(tempdir)
            ...
    """

    if not tempdir_root:
        raise ValueError("tempdir_root cannot be empty string or None")

    tempdir_root = os.path.abspath(str(tempdir_root))
    os.makedirs(tempdir_root, exist_ok=True)

    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            with TemporaryDirectory(dir=tempdir_root, suffix=suffix) as f:
                args = args + (f,)
                return func(*args, **kwargs)

        return inner

    return decorator


@METRICS.timer_decorator("upload_archive")
@api_require_POST
@csrf_exempt
@api_login_required
@api_any_permission_required("upload.upload_symbols", "upload.upload_try_symbols")
@make_tempdir(tempdir_root=settings.UPLOAD_TEMPDIR)
def upload_archive(request, upload_workspace):
    try:
        for name in request.FILES:
            upload_ = request.FILES[name]
            file_listing = dump_and_extract(upload_workspace, upload_, name)
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
                    download_name = os.path.join(upload_workspace, name)
                    session = session_with_retries(default_timeout=(5, 300))
                    with METRICS.timer("upload_download_by_url"):
                        response_stream = session.get(url, stream=True)
                        # NOTE(willkg): The UploadByDownloadForm handles most errors
                        # when it does a HEAD, so this mostly covers transient errors
                        # between the HEAD and this GET request.
                        if response_stream.status_code != 200:
                            return http.JsonResponse(
                                {
                                    "error": "non-200 status code when retrieving %s"
                                    % url
                                },
                                status=400,
                            )

                        with open(download_name, "wb") as f:
                            # Read 1MB at a time
                            chunk_size = 1024 * 1024
                            stream = response_stream.iter_content(chunk_size=chunk_size)
                            count_chunks = 0
                            start = time.perf_counter()
                            for chunk in stream:
                                if chunk:  # filter out keep-alive new chunks
                                    f.write(chunk)
                                count_chunks += 1
                            end = time.perf_counter()
                            total_size = chunk_size * count_chunks
                            download_speed = size / (end - start)
                            logger.info(
                                f"Read {count_chunks} chunks of "
                                f"{filesizeformat(chunk_size)} each "
                                f"totalling {filesizeformat(total_size)} "
                                f"({filesizeformat(download_speed)}/s)."
                            )
                    file_listing = dump_and_extract(
                        upload_workspace, download_name, name
                    )
                    os.remove(download_name)
                else:
                    for errors in form.errors.as_data().values():
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
    if is_try_upload is None:
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
        is_try_upload = not request.user.has_perm("upload.upload_symbols")
    else:
        # In case it's passed in as a string
        is_try_upload = bool(is_try_upload)

    backend = symbol_storage().get_upload_backend(is_try_upload)

    # Make a hash string that represents every file listing in the archive.
    # Do this by making a string first out of all files listed.

    content = "\n".join(
        f"{x.name}:{x.size}" for x in sorted(file_listing, key=lambda x: x.name)
    )
    # The MD5 is just used to make the temporary S3 file unique in name
    # if the client uploads with the same filename in quick succession.
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:30]  # nosec

    # Always create the Upload object no matter what happens next.
    # If all individual file uploads work out, we say this is complete.
    upload_obj = Upload.objects.create(
        user=request.user,
        filename=name,
        bucket_name=backend.bucket,
        size=size,
        download_url=url,
        redirect_urls=redirect_urls,
        content_hash=content_hash,
        try_symbols=is_try_upload,
    )

    ignored_keys = []
    skipped_keys = []

    file_uploads_created = 0
    uploaded_symbol_keys = []
    key_to_symbol_keys = {}
    future_to_key = {}
    for member in file_listing:
        if _ignore_member_file(member.name):
            ignored_keys.append(member.name)
            continue
        # We need to know and remember, for every file attempted,
        # what that name corresponds to as a "symbol key".
        # A symbol key is, for example, ('xul.pdb', 'A7D6F1BBA7D6F1BB1')
        symbol_key = tuple(member.name.split("/")[:2])
        key_to_symbol_keys[member.name] = symbol_key
        future_to_key[
            executor.submit(
                upload_file_upload,
                backend=backend,
                key_name=member.name,
                file_path=member.path,
                upload=upload_obj,
            )
        ] = member.name
    # Now lets wait for them all to finish and we'll see which ones
    # were skipped and which ones were created.
    for future in concurrent.futures.as_completed(future_to_key):
        file_upload = future.result()
        if file_upload:
            file_uploads_created += 1
            uploaded_symbol_keys.append(key_to_symbol_keys[file_upload.key])
        else:
            skipped_keys.append(future_to_key[future])
            METRICS.incr("upload_file_upload_skip", 1)

    if file_uploads_created:
        logger.info(f"Created {file_uploads_created} FileUpload objects")
    else:
        logger.info(f"No file uploads created for {upload_obj!r}")

    Upload.objects.filter(id=upload_obj.id).update(
        skipped_keys=skipped_keys or None,
        ignored_keys=ignored_keys or None,
        completed_at=timezone.now(),
    )

    METRICS.incr(
        "upload_uploads", tags=[f"try:{is_try_upload}", f"bucket:{backend.bucket}"]
    )

    return http.JsonResponse({"upload": _serialize_upload(upload_obj)}, status=201)


def _serialize_upload(upload):
    return {
        "id": upload.id,
        "size": upload.size,
        "filename": upload.filename,
        "bucket": upload.bucket_name,
        "download_url": upload.download_url,
        "try_symbols": upload.try_symbols,
        "redirect_urls": upload.redirect_urls or [],
        "completed_at": upload.completed_at,
        "created_at": upload.created_at,
        "user": upload.user.email,
        "skipped_keys": upload.skipped_keys or [],
    }
