# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
from io import BytesIO, StringIO
import logging
import os
from pathlib import Path
from unittest import mock

from botocore.exceptions import ClientError
import pytest
from requests.exceptions import ConnectionError, RetryError

from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from tecken.base.symboldownloader import SymbolDownloader
from tecken.tokens.models import Token
from tecken.upload import utils
from tecken.upload.forms import UploadByDownloadForm, UploadByDownloadRemoteError
from tecken.upload.models import Upload, FileUpload
from tecken.upload.utils import (
    dump_and_extract,
    key_existing,
    should_compressed_key,
    get_key_content_type,
)
from tecken.upload.views import get_bucket_info


def _join(x):
    return os.path.join(os.path.dirname(__file__), x)


ZIP_FILE = _join("sample.zip")
ZIP_FILE_WITH_IGNORABLE_FILES = _join("sample-with-ignorable-files.zip")
INVALID_ZIP_FILE = _join("invalid.zip")
INVALID_CHARACTERS_ZIP_FILE = _join("invalid-characters.zip")
ACTUALLY_NOT_ZIP_FILE = _join("notazipdespiteitsname.zip")
DUPLICATED_SAME_SIZE_ZIP_FILE = _join("duplicated-same-size.zip")
DUPLICATED_DIFFERENT_SIZE_ZIP_FILE = _join("duplicated-different-size.zip")


def test_dump_and_extract(tmpdir):
    with open(ZIP_FILE, "rb") as f:
        file_listings = dump_and_extract(str(tmpdir), f, ZIP_FILE)

    # That .zip file has multiple files in it so it's hard to rely on the order.
    assert len(file_listings) == 3
    for file_listing in file_listings:
        assert file_listing.path
        assert os.path.isfile(file_listing.path)
        assert file_listing.name
        assert not file_listing.name.startswith("/")
        assert file_listing.size
        assert file_listing.size == os.stat(file_listing.path).st_size

    # Inside the tmpdir there should now exist these files. Know thy fixtures...
    assert Path(tmpdir / "xpcshell.dbg").is_dir()
    assert Path(tmpdir / "flag").is_dir()
    assert Path(tmpdir / "build-symbols.txt").is_file()


def test_dump_and_extract_duplicate_name_same_size(tmpdir):
    with open(DUPLICATED_SAME_SIZE_ZIP_FILE, "rb") as f:
        file_listings = dump_and_extract(str(tmpdir), f, DUPLICATED_SAME_SIZE_ZIP_FILE)
    # Even though the file contains 2 files.
    assert len(file_listings) == 1


def test_should_compressed_key(settings):
    settings.COMPRESS_EXTENSIONS = ["bar"]
    assert should_compressed_key("foo.bar")
    assert should_compressed_key("foo.BAR")
    assert not should_compressed_key("foo.exe")


def test_get_key_content_type(settings):
    settings.MIME_OVERRIDES = {"html": "text/html"}
    assert get_key_content_type("foo.bar") is None
    assert get_key_content_type("foo.html") == "text/html"
    assert get_key_content_type("foo.HTML") == "text/html"


def test_upload_archive_with_ignorable_files(
    client,
    db,
    s3_helper,
    uploaderuser,
):
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    url = reverse("upload:upload_archive")
    with open(ZIP_FILE_WITH_IGNORABLE_FILES, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert sorted(upload.ignored_keys) == [
            "build-symbols.txt",
            "flag/.DS_Store",
            "xpcshell.dbg/A7D6F1BB18CD4CB48/.DS_Store",
        ]

    assert FileUpload.objects.all().count() == 2


def test_upload_archive_happy_path(
    client,
    db,
    s3_helper,
    uploaderuser,
    metricsmock,
):
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    # Upload one of the files so that when the upload happens, it's an update.
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/flag/deadbeef/flag.jpeg",
        data=b"abc123",
    )

    url = reverse("upload:upload_archive")
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

    (upload,) = Upload.objects.all()
    assert upload.user == uploaderuser
    assert upload.filename == "file.zip"
    assert upload.completed_at
    # Based on `ls -l tests/sample.zip` knowledge
    assert upload.size == 70398
    # This is predictable and shouldn't change unless the fixture file used changes.
    assert upload.content_hash == "984270ef458d9d1e27e8d844ad52a9"
    assert upload.bucket_name == "publicbucket"
    assert upload.bucket_region is None
    assert upload.bucket_endpoint_url == "http://localstack:4566"
    assert upload.skipped_keys is None
    assert upload.ignored_keys == ["build-symbols.txt"]

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="publicbucket",
        key="v1/flag/deadbeef/flag.jpeg",
        compressed=False,
        # This existed in the bucket before this upload, so this is an update
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="publicbucket",
        key="v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that it's been
        # compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 12
    # It's impossible to predict, the order of some metrics records because of the use
    # of ThreadPoolExecutor. So we can't look at them in the exact order.
    all_keys = [x.key for x in records]
    assert all_keys.count("tecken.upload_file_exists") == 2
    assert all_keys.count("tecken.upload_gzip_payload") == 1  # only 1 .sym
    assert all_keys.count("tecken.upload_put_object") == 2
    assert all_keys.count("tecken.upload_dump_and_extract") == 1
    assert all_keys.count("tecken.upload_file_upload_upload") == 2
    assert all_keys.count("tecken.upload_file_upload") == 2
    assert all_keys.count("tecken.upload_uploads") == 1
    assert all_keys.count("tecken.upload_archive") == 1


def test_upload_try_symbols_happy_path(
    client,
    db,
    s3_helper,
    uploaderuser,
):
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_try_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    # Upload one of the files so that when the upload happens, it's an update.
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="try/v1/flag/deadbeef/flag.jpeg",
        data=b"abc123",
    )

    url = reverse("upload:upload_archive")

    with open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

    (upload,) = Upload.objects.all()
    assert upload.user == uploaderuser
    assert upload.filename == "file.zip"
    assert upload.completed_at
    # Based on `ls -l tests/sample.zip` knowledge
    assert upload.size == 70398
    # This is predictable and shouldn't change unless the fixture file used changes.
    assert upload.content_hash == "984270ef458d9d1e27e8d844ad52a9"
    assert upload.bucket_name == "publicbucket"
    assert upload.bucket_region is None
    assert upload.bucket_endpoint_url == "http://localstack:4566"
    assert upload.skipped_keys is None
    assert upload.ignored_keys == ["build-symbols.txt"]
    assert upload.try_symbols is True

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="publicbucket",
        key="try/v1/flag/deadbeef/flag.jpeg",
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="publicbucket",
        key="try/v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


def test_upload_archive_one_uploaded_one_skipped(
    client,
    db,
    s3_helper,
    tmp_path,
    uploaderuser,
):
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    # Upload flag.jpeg from the zip file into the bucket so it's already there
    # and gets ignored when it's uploaded
    rootdir = str(tmp_path)
    with open(ZIP_FILE, "rb") as fp:
        dump_and_extract(rootdir, fp, ZIP_FILE)
    flag_jpeg_path = tmp_path / "flag/deadbeef/flag.jpeg"
    with open(flag_jpeg_path, "rb") as fp:
        s3_helper.upload_fileobj(
            bucket_name="publicbucket",
            key="v1/flag/deadbeef/flag.jpeg",
            data=fp.read(),
        )

    url = reverse("upload:upload_archive")
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

    (upload,) = Upload.objects.all()
    assert upload.user == uploaderuser
    # assert upload.inbox_key is None
    # assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
    assert upload.filename == "file.zip"
    assert upload.completed_at
    # based on `ls -l tests/sample.zip` knowledge
    assert upload.size == 70398
    assert upload.bucket_name == "publicbucket"
    assert upload.bucket_region is None
    assert upload.bucket_endpoint_url == "http://localstack:4566"
    assert upload.skipped_keys == ["v1/flag/deadbeef/flag.jpeg"]
    assert upload.ignored_keys == ["build-symbols.txt"]

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload,
        bucket_name="publicbucket",
        key="v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


def test_key_existing_caching(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="somefile.txt",
        data=b"abc123",
    )

    client = s3_helper.conn

    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 6
    assert metadata == {}

    # Change the file, but don't invalidate the cache
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="somefile.txt",
        data=b"abc123123",
    )

    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 6
    assert metadata == {}

    # Invalidate the cache and make sure the size changes
    key_existing.invalidate(client, "publicbucket", "somefile.txt")
    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 9
    assert metadata == {}


def test_key_existing_size_caching_not_found(s3_helper):
    s3_helper.create_bucket("publicbucket")
    client = s3_helper.conn

    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 0
    assert metadata is None

    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 0
    assert metadata is None

    key_existing.invalidate(client, "publicbucket", "somefile.txt")
    size, metadata = key_existing(client, "publicbucket", "somefile.txt")
    assert size == 0
    assert metadata is None


def test_upload_archive_key_lookup_cached(
    client,
    db,
    s3_helper,
    uploaderuser,
):
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    url = reverse("upload:upload_archive")

    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        assert FileUpload.objects.all().count() == 2

    # Upload the same file again. This time some of the S3 HeadObject operations should
    # benefit from a cache.
    #
    # FIXME(willkg): we're not testing whether some of the lookups were from the cache
    # or not
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 2
        assert FileUpload.objects.all().count() == 2

    # Upload the same file again. This time some of the S3 HeadObject operations should
    # benefit from a cache.
    #
    # FIXME(willkg): we're not testing whether some of the lookups were from the cache
    # or not
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 3
        assert FileUpload.objects.all().count() == 2


def test_upload_archive_key_lookup_cached_without_metadata(
    client,
    db,
    s3_helper,
    uploaderuser,
):
    """Same as test_upload_archive_key_lookup_cached() but without
    any metadata."""

    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    url = reverse("upload:upload_archive")

    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        assert FileUpload.objects.all().count() == 2

    # Upload the same file again. This time some of the S3 HeadObject operations should
    # benefit from a cache.
    #
    # FIXME(willkg): we're not verifying the caching
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 2
        assert FileUpload.objects.all().count() == 2

    # Upload the same file again. This time some of the S3 HeadObject operations should
    # benefit from a cache.
    #
    # FIXME(willkg): we're not verifying the caching
    with open(ZIP_FILE, "rb") as fp:
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 3
        assert FileUpload.objects.all().count() == 2


def test_upload_archive_one_uploaded_one_errored(client, db, botomock, uploaderuser):
    # NOTE(willkg): keeping botomock here because it tests a very specific situation
    # where one of the uploaded files fails to upload to S3
    class AnyUnrecognizedError(Exception):
        """Doesn't matter much what the exception is. What matters is that
        it happens during a boto call."""

    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "publicbucket"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v1/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Not found at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            raise AnyUnrecognizedError("stop!")

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        with pytest.raises(AnyUnrecognizedError):
            client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)

        (upload,) = Upload.objects.all()
        assert upload.user == uploaderuser
        assert not upload.completed_at

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload, key="v1/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
    )


def test_upload_archive_with_cache_invalidation(
    client,
    db,
    s3_helper,
    uploaderuser,
    settings,
):
    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    utils.downloader = downloader

    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)

    s3_helper.create_bucket("publicbucket")

    # NOTE(willkg): this is a file in ZIP_FILE
    module = "xpcshell.dbg"
    debugid = "A7D6F1BB18CD4CB48"  # NOTE(willkg): this is not a valid debug id. :(
    debugfn = "xpcshell.sym"

    with open(ZIP_FILE, "rb") as fp:
        # First time -- not there
        assert not downloader.has_symbol(module, debugid, debugfn)

        url = reverse("upload:upload_archive")
        response = client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        # Second time is there
        assert downloader.has_symbol(module, debugid, debugfn)


def test_upload_archive_by_url(
    client,
    db,
    s3_helper,
    uploaderuser,
    settings,
    requestsmock,
):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = [
        "allowed.example.com",
        "download.example.com",
    ]
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    s3_helper.create_bucket("publicbucket")

    url = reverse("upload:upload_archive")

    # Test an HTTP url.
    response = client.post(
        url,
        data={"url": "http://example.com/symbols.zip"},
        HTTP_AUTH_TOKEN=token.key,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Insecure URL"

    # Test a url from a disallowed host.
    response = client.post(
        url,
        data={"url": "https://notallowed.example.com/symbols.zip"},
        HTTP_AUTH_TOKEN=token.key,
    )
    assert response.status_code == 400
    assert response.json()["error"] == (
        "Not an allowed domain ('notallowed.example.com') to download from."
    )

    with open(ZIP_FILE, "rb") as fp:
        # Lastly, the happy path
        zip_file_content = fp.read()
        requestsmock.head(
            "https://allowed.example.com/symbols.zip",
            text="Found",
            status_code=302,
            headers={"Location": "https://download.example.com/symbols.zip"},
        )
        requestsmock.head(
            "https://download.example.com/symbols.zip",
            content=b"",
            status_code=200,
            headers={"Content-Length": str(len(zip_file_content))},
        )

        requestsmock.head(
            "https://allowed.example.com/bad.zip",
            text="Found",
            status_code=302,
            headers={"Location": "https://bad.example.com/symbols.zip"},
        )
        requestsmock.get(
            "https://allowed.example.com/symbols.zip",
            content=zip_file_content,
            status_code=200,
        )

    response = client.post(
        url,
        data={"url": "https://allowed.example.com/symbols.zip"},
        HTTP_AUTH_TOKEN=token.key,
    )
    assert response.status_code == 201
    assert response.json()["upload"]["download_url"] == (
        "https://allowed.example.com/symbols.zip"
    )
    assert response.json()["upload"]["redirect_urls"] == [
        "https://download.example.com/symbols.zip"
    ]

    (upload,) = Upload.objects.all()
    assert upload.download_url
    assert upload.redirect_urls
    assert upload.user == uploaderuser
    assert upload.filename == "symbols.zip"
    assert upload.completed_at

    assert FileUpload.objects.filter(upload=upload).count() == 2


def test_upload_archive_by_url_remote_error(
    client, db, uploaderuser, settings, requestsmock
):
    requestsmock.head("https://allowed.example.com/symbols.zip", exc=ConnectionError)

    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")
    response = client.post(
        url,
        data={"url": "https://allowed.example.com/symbols.zip"},
        HTTP_AUTH_TOKEN=token.key,
    )
    assert response.status_code == 500
    assert response.json()["error"] == (
        "ConnectionError trying to open https://allowed.example.com/symbols.zip"
    )


def test_upload_client_bad_request(client, db, uploaderuser, settings):
    url = reverse("upload:upload_archive")
    response = client.get(url)
    assert response.status_code == 405
    error_msg = "Method Not Allowed (GET): /upload/"
    assert response.json()["error"] == error_msg

    response = client.post(url)
    assert response.status_code == 403
    error_msg = "This requires an Auth-Token to authenticate the request"
    assert response.json()["error"] == error_msg

    token = Token.objects.create(user=uploaderuser)
    response = client.post(url, HTTP_AUTH_TOKEN=token.key)
    # will also fail because of lack of permission
    assert response.status_code == 403
    assert response.json()["error"] == "Forbidden"

    # so let's fix that
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)

    response = client.post(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 400
    error_msg = "Must be multipart form data with at least one file"
    assert response.json()["error"] == error_msg

    # Upload an empty file
    empty_fileobject = BytesIO()
    response = client.post(
        url, {"myfile.zip": empty_fileobject}, HTTP_AUTH_TOKEN=token.key
    )
    assert response.status_code == 400
    assert response.json()["error"] == "File is not a zip file"

    # Unrecognized file extension
    with open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"myfile.rar": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        assert response.json()["error"] == (
            'Unrecognized archive file extension ".rar"'
        )

    settings.DISALLOWED_SYMBOLS_SNIPPETS = ("xpcshell.sym",)

    with open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = (
            "Content of archive file contains the snippet "
            "'xpcshell.sym' which is not allowed"
        )
        assert response.json()["error"] == error_msg

    # Undo that setting override
    settings.DISALLOWED_SYMBOLS_SNIPPETS = ("nothing",)

    # Now upload a file that doesn't have the right filename patterns
    with open(INVALID_ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = (
            "Unrecognized file pattern. Should only be "
            "<module>/<hex>/<file> or <name>-symbols.txt and nothing else. "
            "(First unrecognized pattern was xpcshell.sym)"
        )
        assert response.json()["error"] == error_msg

    # Now upload a file that isn't a zip file
    with open(ACTUALLY_NOT_ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = "File is not a zip file"
        assert response.json()["error"] == error_msg

    # Now upload a file that contains folders and file names that contains
    # invalid characters.
    with open(INVALID_CHARACTERS_ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = (
            "Invalid character in filename " "'xpcfoo.dbg/A7D6F1BB18CD4CB48/p%eter.sym'"
        )
        assert response.json()["error"] == error_msg


def test_upload_duplicate_files_in_zip_different_name(client, db, uploaderuser):
    url = reverse("upload:upload_archive")
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)

    # Upload a file whose members have some repeated name AND different size
    with open(DUPLICATED_DIFFERENT_SIZE_ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = (
            "The zipfile buffer contains two files both called "
            "foo.pdb/50FEB8DBDC024C66B42193D881CE80E12/ntdll.sym and they have "
            "difference sizes (24 != 39)"
        )
        assert response.json()["error"] == error_msg


def test_upload_client_unrecognized_bucket(client, db, s3_helper, uploaderuser):
    """The upload view raises an error if you try to upload into a bucket
    that doesn't exist."""
    token = Token.objects.create(user=uploaderuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    with open(ZIP_FILE, "rb") as fp, pytest.raises(ImproperlyConfigured):
        client.post(url, {"file.zip": fp}, HTTP_AUTH_TOKEN=token.key)


def test_get_bucket_info(settings, uploaderuser):
    settings.UPLOAD_DEFAULT_URL = "http://s3.amazonaws.com/some-bucket"
    bucket_info = get_bucket_info(uploaderuser)
    assert bucket_info.name == "some-bucket"
    assert bucket_info.endpoint_url is None
    assert bucket_info.region is None
    assert not bucket_info.try_symbols

    settings.UPLOAD_DEFAULT_URL = "http://s3-eu-west-2.amazonaws.com/some-bucket"
    bucket_info = get_bucket_info(uploaderuser)
    assert bucket_info.name == "some-bucket"
    assert bucket_info.endpoint_url is None
    assert bucket_info.region == "eu-west-2"

    settings.UPLOAD_DEFAULT_URL = "http://s3.example.com/buck/prefix"
    bucket_info = get_bucket_info(uploaderuser)
    assert bucket_info.name == "buck"
    assert bucket_info.endpoint_url == "http://s3.example.com"
    assert bucket_info.region is None


def test_UploadByDownloadForm_happy_path(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head(
        "https://allowed.example.com/symbols.zip",
        content=b"content",
        status_code=200,
        headers={"Content-Length": "1234"},
    )

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    assert form.is_valid()
    assert form.cleaned_data["url"] == ("https://allowed.example.com/symbols.zip")
    assert form.cleaned_data["upload"]["name"] == "symbols.zip"
    assert form.cleaned_data["upload"]["size"] == 1234
    assert form.cleaned_data["upload"]["redirect_urls"] == []


def test_UploadByDownloadForm_redirects(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head(
        "https://allowed.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )

    requestsmock.head(
        "https://download.example.com/symbols.zip",
        content=b"content",
        status_code=200,
        headers={"Content-Length": "1234"},
    )

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    assert form.is_valid()
    assert form.cleaned_data["url"] == ("https://allowed.example.com/symbols.zip")
    assert form.cleaned_data["upload"]["name"] == "symbols.zip"
    assert form.cleaned_data["upload"]["size"] == 1234
    assert form.cleaned_data["upload"]["redirect_urls"] == [
        "https://download.example.com/symbols.zip"
    ]


def test_UploadByDownloadForm_redirects_bad(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head(
        "https://allowed.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )

    requestsmock.head(
        "https://download.example.com/symbols.zip",
        content=b"Internal Server Error",
        status_code=500,
    )

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()


def test_UploadByDownloadForm_connectionerrors(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head("https://allowed.example.com/symbols.zip", exc=ConnectionError)

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()

    # Suppose the HEAD request goes to another URL which eventually
    # raises a ConnectionError.

    requestsmock.head(
        "https://allowed.example.com/redirect.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/busted.zip"},
    )
    requestsmock.head("https://download.example.com/busted.zip", exc=ConnectionError)
    form = UploadByDownloadForm({"url": "https://allowed.example.com/redirect.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()

    # Suppose the URL simply is not found.
    requestsmock.head(
        "https://allowed.example.com/404.zip", text="Not Found", status_code=404
    )
    form = UploadByDownloadForm({"url": "https://allowed.example.com/404.zip"})
    assert not form.is_valid()
    (validation_errors,) = form.errors.as_data().values()
    assert validation_errors[0].message == (
        "https://allowed.example.com/404.zip can't be found (404)"
    )


def test_UploadByDownloadForm_retryerror(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head("https://allowed.example.com/symbols.zip", exc=RetryError)

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()


def test_UploadByDownloadForm_redirection_exhaustion(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["allowed.example.com"]

    requestsmock.head(
        "https://allowed.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )

    requestsmock.head(
        "https://download.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )

    form = UploadByDownloadForm({"url": "https://allowed.example.com/symbols.zip"})
    assert not form.is_valid()
    (validation_errors,) = form.errors.as_data().values()
    assert "Too many redirects" in validation_errors[0].message


def test_cleanse_upload_records(db, fakeuser):
    """cleanse_upload deletes appropriate records"""
    today = timezone.now()
    try_cutoff = today - datetime.timedelta(days=30)
    reg_cutoff = today - datetime.timedelta(days=365 * 2)

    # Create a few uploads
    upload = Upload.objects.create(
        user=fakeuser, filename="reg-1.zip", size=100, try_symbols=False
    )
    FileUpload.objects.create(upload=upload, key="reg-1-1.sym", size=100)
    FileUpload.objects.create(upload=upload, key="reg-1-2.sym", size=100)

    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = reg_cutoff - datetime.timedelta(days=1)
        upload = Upload.objects.create(
            user=fakeuser, filename="reg-2.zip", size=100, try_symbols=False
        )
        FileUpload.objects.create(upload=upload, key="reg-2-1.sym", size=100)
        FileUpload.objects.create(upload=upload, key="reg-2-2.sym", size=100)

    # Create a few try uploads
    upload = Upload.objects.create(
        user=fakeuser, filename="try-1.zip", size=100, try_symbols=True
    )
    FileUpload.objects.create(upload=upload, key="try-1-1.sym", size=100)
    FileUpload.objects.create(upload=upload, key="try-1-2.sym", size=100)

    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = try_cutoff - datetime.timedelta(days=1)
        upload = Upload.objects.create(
            user=fakeuser, filename="try-2.zip", size=100, try_symbols=True
        )
        FileUpload.objects.create(upload=upload, key="try-2-1.sym", size=100)
        FileUpload.objects.create(upload=upload, key="try-2-2.sym", size=100)

    stdout = StringIO()
    call_command("cleanse_upload", dry_run=False, stdout=stdout)

    assert "DRY RUN" not in stdout.getvalue()

    upload_filenames = list(
        Upload.objects.order_by("filename").values_list("filename", flat=True)
    )
    assert upload_filenames == ["reg-1.zip", "try-1.zip"]

    file_keys = list(FileUpload.objects.order_by("key").values_list("key", flat=True))
    assert file_keys == ["reg-1-1.sym", "reg-1-2.sym", "try-1-1.sym", "try-1-2.sym"]


def test_cleanse_upload_records_dry_run(db, fakeuser):
    """cleanse_upload dry_run doesn't delete records"""
    today = timezone.now()
    try_cutoff = today - datetime.timedelta(days=30)
    reg_cutoff = today - datetime.timedelta(days=365 * 2)

    # Create a few uploads
    upload = Upload.objects.create(
        user=fakeuser, filename="reg-1.zip", size=100, try_symbols=False
    )
    FileUpload.objects.create(upload=upload, key="reg-1-1.sym", size=100)
    FileUpload.objects.create(upload=upload, key="reg-1-2.sym", size=100)

    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = reg_cutoff - datetime.timedelta(days=1)
        upload = Upload.objects.create(
            user=fakeuser, filename="reg-2.zip", size=100, try_symbols=False
        )
        FileUpload.objects.create(upload=upload, key="reg-2-1.sym", size=100)
        FileUpload.objects.create(upload=upload, key="reg-2-2.sym", size=100)

    # Create a few try uploads
    upload = Upload.objects.create(
        user=fakeuser, filename="try-1.zip", size=100, try_symbols=True
    )
    FileUpload.objects.create(upload=upload, key="try-1-1.sym", size=100)
    FileUpload.objects.create(upload=upload, key="try-1-2.sym", size=100)

    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = try_cutoff - datetime.timedelta(days=1)
        upload = Upload.objects.create(
            user=fakeuser, filename="try-2.zip", size=100, try_symbols=True
        )
        FileUpload.objects.create(upload=upload, key="try-2-1.sym", size=100)
        FileUpload.objects.create(upload=upload, key="try-2-2.sym", size=100)

    stdout = StringIO()
    call_command("cleanse_upload", dry_run=True, stdout=stdout)

    assert "DRY RUN" in stdout.getvalue()

    upload_filenames = list(
        Upload.objects.order_by("filename").values_list("filename", flat=True)
    )
    assert upload_filenames == ["reg-1.zip", "reg-2.zip", "try-1.zip", "try-2.zip"]

    file_keys = list(FileUpload.objects.order_by("key").values_list("key", flat=True))
    assert file_keys == [
        "reg-1-1.sym",
        "reg-1-2.sym",
        "reg-2-1.sym",
        "reg-2-2.sym",
        "try-1-1.sym",
        "try-1-2.sym",
        "try-2-1.sym",
        "try-2-2.sym",
    ]


class Test_remove_orphaned_files:
    def test_no_files(self, db, settings, tmp_path, caplog):
        caplog.set_level(logging.INFO)

        tempdir = str(tmp_path)
        settings.UPLOAD_TEMPDIR = tempdir
        settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF = 5

        call_command("remove_orphaned_files", verbose=True)

        # Make sure we've got the right expires value
        assert "expires: 5 (minutes)" in caplog.text

        # Make sure we're watching the correct path
        assert f"watchdir: {tempdir!r}" in caplog.text

        # Make sure there's no error output
        error_records = [rec for rec in caplog.records if rec.levelname == "ERROR"]
        assert len(error_records) == 0

    def test_recent_files(self, db, settings, tmp_path):
        tempdir = str(tmp_path)
        settings.UPLOAD_TEMPDIR = tempdir
        settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF = 5

        # Create a couple of directories with recent files in them
        (tmp_path / "upload1").mkdir(parents=True)
        (tmp_path / "upload1" / "file1.sym").write_text("abcde")
        (tmp_path / "upload1" / "file2.sym").write_text("abcde")
        (tmp_path / "upload1" / "file3.sym").write_text("abcde")
        (tmp_path / "upload2").mkdir(parents=True)
        (tmp_path / "upload2" / "file1.sym").write_text("abcde")
        contents = [str(path)[len(str(tmp_path)) :] for path in tmp_path.glob("**/*")]
        contents.sort()
        assert contents == [
            "/upload1",
            "/upload1/file1.sym",
            "/upload1/file2.sym",
            "/upload1/file3.sym",
            "/upload2",
            "/upload2/file1.sym",
        ]

        # Run the command
        call_command("remove_orphaned_files", verbose=True)

        # Asssert nothing got deleted
        contents = [str(path)[len(str(tmp_path)) :] for path in tmp_path.glob("**/*")]
        contents.sort()
        assert contents == [
            "/upload1",
            "/upload1/file1.sym",
            "/upload1/file2.sym",
            "/upload1/file3.sym",
            "/upload2",
            "/upload2/file1.sym",
        ]

    def test_orphaned_files(self, db, settings, tmp_path, caplog, metricsmock):
        tempdir = str(tmp_path)
        settings.UPLOAD_TEMPDIR = tempdir
        settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF = 5

        def create_file(path, delta_minutes):
            now = datetime.datetime.now() - datetime.timedelta(minutes=delta_minutes)
            now_epoch = now.timestamp()
            path.write_text("abcde")
            os.utime(path, times=(now_epoch, now_epoch))

        # Create a couple of directories with recent files in them
        (tmp_path / "upload1").mkdir(parents=True)
        create_file(tmp_path / "upload1" / "file1.sym", delta_minutes=12)
        create_file(tmp_path / "upload1" / "file2.sym", delta_minutes=11)
        create_file(tmp_path / "upload1" / "file3.sym", delta_minutes=10)

        (tmp_path / "upload2").mkdir(parents=True)
        create_file(tmp_path / "upload2" / "file1.sym", delta_minutes=3)

        contents = [str(path)[len(str(tmp_path)) :] for path in tmp_path.glob("**/*")]
        contents.sort()
        assert contents == [
            "/upload1",
            "/upload1/file1.sym",
            "/upload1/file2.sym",
            "/upload1/file3.sym",
            "/upload2",
            "/upload2/file1.sym",
        ]

        # Run the command
        call_command("remove_orphaned_files", verbose=True)

        # Asssert files older than 5 minutes (our cutoff) are deleted
        #
        # NOTE(willkg): the code doesn't clean up empty directories, so those will
        # still exist.
        contents = [str(path)[len(str(tmp_path)) :] for path in tmp_path.glob("**/*")]
        contents.sort()
        assert contents == [
            "/upload1",
            "/upload2",
            "/upload2/file1.sym",
        ]

        # Verify that the stdout says these were deleted
        for fn in ["file1.sym", "file2.sym", "file3.sym"]:
            path = str(tmp_path / "upload1" / fn)
            assert f"deleted file: {path}, 5b" in caplog.text

        # Verify there's no error output
        error_records = [rec for rec in caplog.records if rec.levelname == "ERROR"]
        assert len(error_records) == 0
        assert "ERROR" not in caplog.text

        # Assert metrics are emitted
        delete_incr = metricsmock.filter_records(
            "incr", stat="tecken.remove_orphaned_files.delete_file"
        )
        assert len(delete_incr) == 3

    def test_errors(self, db, settings, tmp_path, monkeypatch, caplog, metricsmock):
        tempdir = str(tmp_path)
        settings.UPLOAD_TEMPDIR = tempdir
        settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF = 5

        # Create a directory with an old file in it
        (tmp_path / "upload1").mkdir(parents=True)
        path = tmp_path / "upload1" / "file1.sym"
        now = datetime.datetime.now() - datetime.timedelta(minutes=10)
        now_epoch = now.timestamp()
        path.write_text("abcde")
        os.utime(path, times=(now_epoch, now_epoch))

        contents = [str(path)[len(str(tmp_path)) :] for path in tmp_path.glob("**/*")]
        contents.sort()
        assert contents == ["/upload1", "/upload1/file1.sym"]

        # Monkeypatch os.path.getmtime to get the mtime, delete the file, and return the
        # mtime so as to simulate a race condition between getting the mtime and getting
        # the size
        original_getmtime = os.path.getmtime

        def adjusted_getmtime(fn):
            mtime = original_getmtime(fn)
            os.remove(fn)
            return mtime

        monkeypatch.setattr(os.path, "getmtime", adjusted_getmtime)

        # Run the command
        call_command("remove_orphaned_files", verbose=True)

        # Assert message is logged
        assert f"error getting size: {str(path)}" in caplog.text
        assert "FileNotFound" in caplog.text

        # Assert metric is emitted
        incr_records = metricsmock.filter_records(
            "incr", stat="tecken.remove_orphaned_files.delete_file_error"
        )
        assert len(incr_records) == 1
