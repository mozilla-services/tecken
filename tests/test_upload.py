# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
from io import BytesIO
from unittest import mock

import pytest
from botocore.exceptions import ClientError
from requests.exceptions import ConnectionError, RetryError

from django.urls import reverse
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from tecken.storage import StorageBucket
from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload, UploadsCreated
from tecken.upload import utils
from tecken.base.symboldownloader import SymbolDownloader
from tecken.upload.views import (
    NoPossibleBucketName,
    get_bucket_info,
    get_possible_bucket_urls,
)
from tecken.upload.forms import UploadByDownloadForm, UploadByDownloadRemoteError
from tecken.upload.utils import (
    dump_and_extract,
    key_existing,
    should_compressed_key,
    get_key_content_type,
)
from tecken.upload.tasks import update_uploads_created_task


def _join(x):
    return os.path.join(os.path.dirname(__file__), x)


ZIP_FILE = _join("sample.zip")
ZIP_FILE_WITH_IGNORABLE_FILES = _join("sample-with-ignorable-files.zip")
INVALID_ZIP_FILE = _join("invalid.zip")
INVALID_CHARACTERS_ZIP_FILE = _join("invalid-characters.zip")
ACTUALLY_NOT_ZIP_FILE = _join("notazipdespiteitsname.zip")
DUPLICATED_SAME_SIZE_ZIP_FILE = _join("duplicated-same-size.zip")
DUPLICATED_DIFFERENT_SIZE_ZIP_FILE = _join("duplicated-different-size.zip")


class FakeUser:
    def __init__(self, email, perms=("upload.upload_symbols",), is_superuser=False):
        self.email = email
        self.perms = perms
        self.is_superuser = is_superuser

    def has_perm(self, perm):
        return perm in self.perms


def test_dump_and_extract(tmpdir):
    with open(ZIP_FILE, "rb") as f:
        file_listings = dump_and_extract(tmpdir, f, ZIP_FILE)
    # That .zip file has multiple files in it so it's hard to rely
    # on the order.
    assert len(file_listings) == 3
    for file_listing in file_listings:
        assert file_listing.path
        assert os.path.isfile(file_listing.path)
        assert file_listing.name
        assert not file_listing.name.startswith("/")
        assert file_listing.size
        assert file_listing.size == os.stat(file_listing.path).st_size

    # Inside the tmpdir there should now exist these files.
    # Know thy fixtures...
    assert os.path.isdir(os.path.join(tmpdir, "xpcshell.dbg"))
    assert os.path.isdir(os.path.join(tmpdir, "flag"))
    assert os.path.isfile(os.path.join(tmpdir, "build-symbols.txt"))


def test_dump_and_extract_duplicate_name_same_size(tmpdir):
    with open(DUPLICATED_SAME_SIZE_ZIP_FILE, "rb") as f:
        file_listings = dump_and_extract(tmpdir, f, DUPLICATED_SAME_SIZE_ZIP_FILE)
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


@pytest.mark.django_db
def test_upload_archive_custom_bucket_name(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
    settings,
):
    """Pretend that the user specifies a particular custom bucket name."""

    bucket_name = "peterbe-com"
    assert [
        url for url in settings.UPLOAD_URL_EXCEPTIONS.values() if bucket_name in url
    ], list(settings.UPLOAD_URL_EXCEPTIONS.values())

    def mock_api_call(self, operation_name, api_params):
        assert api_params["Bucket"] == bucket_name
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v0/flag/deadbeef/flag.jpeg"
        ):
            # correct size, no need to upload
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # wrong size, code will upload it as a changed file
            return {"ContentLength": 100}

        if operation_name == "PutObject" and api_params["Key"] == (
            "v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # pretend we actually uploaded it
            return {}

        raise NotImplementedError((operation_name, api_params))

    fakeuser.is_superuser = False  # NOTE!
    fakeuser.save()
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(
            url, {"file.zip": f, "bucket_name": bucket_name}, HTTP_AUTH_TOKEN=token.key
        )
        assert response.status_code == 403

    fakeuser.is_superuser = True  # NOTE!
    fakeuser.save()

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(
            url, {"file.zip": f, "bucket_name": bucket_name}, HTTP_AUTH_TOKEN=token.key
        )
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        assert upload.bucket_name == bucket_name


@pytest.mark.django_db
def test_upload_archive_with_ignorable_files(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
    settings,
):
    # The default upload URL setting uses Google Cloud Storage.
    assert StorageBucket(settings.UPLOAD_DEFAULT_URL).backend == "test-s3"

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            # wrong size for this fixture file, need to upload new
            return {"ContentLength": 100}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # file doesn't exist
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] in (
            "prefix/v0/flag/deadbeef/flag.jpeg",
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        ):
            # pretend we actually uploaded it
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE_WITH_IGNORABLE_FILES, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert sorted(upload.ignored_keys) == [
            "build-symbols.txt",
            "flag/.DS_Store",
            "xpcshell.dbg/A7D6F1BB18CD4CB48/.DS_Store",
        ]

    assert FileUpload.objects.all().count() == 2


@pytest.mark.django_db
def test_upload_archive_happy_path(
    client,
    botomock,
    fakeuser,
    metricsmock,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.
            return {"ContentLength": 1000}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Pretend we don't have this in S3 at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            assert "ContentEncoding" not in api_params
            assert "ContentType" not in api_params
            content = api_params["Body"].read()
            # based on `unzip -l tests/sample.zip` knowledge
            assert len(content) == 69183

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }
        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Because .sym is in settings.COMPRESS_EXTENSIONS
            assert api_params["ContentEncoding"] == "gzip"
            # Because .sym is in settings.MIME_OVERRIDES
            assert api_params["ContentType"] == "text/plain"
            body = api_params["Body"].read()
            assert isinstance(body, bytes)
            # If you look at the fixture 'sample.zip', which is used in
            # these tests you'll see that the file 'xpcshell.sym' is
            # 1156 originally. But we asser that it's now *less* because
            # it should have been gzipped.
            assert len(body) < 1156
            original_content = gzip.decompress(body)
            assert len(original_content) == 1156

            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        assert upload.filename == "file.zip"
        assert upload.completed_at
        # Based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 70398
        # This is predictable and shouldn't change unless the fixture
        # file used changes.
        assert upload.content_hash == "984270ef458d9d1e27e8d844ad52a9"
        assert upload.bucket_name == "private"
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == "https://s3.example.com"
        assert upload.skipped_keys is None
        assert upload.ignored_keys == ["build-symbols.txt"]

    assert len(upload_mock_update_uploads_created_task.all_delay_arguments) == 1

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="private",
        key="prefix/v0/flag/deadbeef/flag.jpeg",
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="private",
        key="prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )

    # Manually execute 'update_uploads_created_task' because it's mocked
    # in the context of the view function.
    update_uploads_created_task()
    uploads_created = UploadsCreated.objects.all().get()
    assert uploads_created.date == timezone.now().date()
    assert uploads_created.count == 1
    assert uploads_created.files == 2
    assert uploads_created.skipped == 0
    assert uploads_created.ignored == 1
    assert uploads_created.size == 70398
    assert uploads_created.size_avg > 0

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 13
    # It's impossible to predict, the order of some metrics records
    # because of the use of ThreadPoolExecutor. So we can't look at them
    # in the exact order.
    all_tags = [x[1] for x in records]
    assert all_tags.count("tecken.upload_file_exists") == 2
    assert all_tags.count("tecken.upload_gzip_payload") == 1  # only 1 .sym
    assert all_tags.count("tecken.upload_put_object") == 2
    assert all_tags.count("tecken.upload_dump_and_extract") == 1
    assert all_tags.count("tecken.upload_file_upload_upload") == 2
    assert all_tags.count("tecken.upload_file_upload") == 2
    assert all_tags.count("tecken.upload_uploads") == 1
    assert all_tags.count("tecken.uploads_created_update") == 1
    assert all_tags[-2] == "tecken.upload_archive"

    invalidate_symbolicate_cache_args = [
        x[0] for x in upload_mock_invalidate_symbolicate_cache.all_delay_arguments
    ]
    # The upload should have triggered a call to
    # tecken.symbolicate.tasks.invalidate_symbolicate_cache
    # one time for these uploaded files
    (call_args,) = invalidate_symbolicate_cache_args
    # And the first (and only argument) should be a list of tuples
    (first_arg,) = call_args
    # Use `sorted()` because the order is unpredictable.
    assert sorted(first_arg) == [
        ("flag", "deadbeef"),
        ("xpcshell.dbg", "A7D6F1BB18CD4CB48"),
    ]


@pytest.mark.django_db
def test_upload_try_symbols_happy_path(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_try_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_TRY_SYMBOLS_URL specifically
        # for tests.
        assert api_params["Bucket"] == "try"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.
            return {"ContentLength": 1000}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Pretend we don't have this in S3 at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            assert "ContentEncoding" not in api_params
            assert "ContentType" not in api_params
            content = api_params["Body"].read()
            # based on `unzip -l tests/sample.zip` knowledge
            assert len(content) == 69183

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }
        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Because .sym is in settings.COMPRESS_EXTENSIONS
            assert api_params["ContentEncoding"] == "gzip"
            # Because .sym is in settings.MIME_OVERRIDES
            assert api_params["ContentType"] == "text/plain"
            body = api_params["Body"].read()
            assert isinstance(body, bytes)
            # If you look at the fixture 'sample.zip', which is used in
            # these tests you'll see that the file 'xpcshell.sym' is
            # 1156 originally. But we asser that it's now *less* because
            # it should have been gzipped.
            assert len(body) < 1156
            original_content = gzip.decompress(body)
            assert len(original_content) == 1156

            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        assert upload.filename == "file.zip"
        assert upload.completed_at
        # Based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 70398
        # This is predictable and shouldn't change unless the fixture
        # file used changes.
        assert upload.content_hash == "984270ef458d9d1e27e8d844ad52a9"
        assert upload.bucket_name == "try"
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == "https://s3.example.com"
        assert upload.skipped_keys is None
        assert upload.ignored_keys == ["build-symbols.txt"]
        assert upload.try_symbols

    assert len(upload_mock_update_uploads_created_task.all_delay_arguments) == 1

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="try",
        key="prefix/v0/flag/deadbeef/flag.jpeg",
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name="try",
        key="prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


@pytest.mark.django_db
def test_upload_archive_one_uploaded_one_skipped(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"

        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            # file exists with same size
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Not found at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Successfully uploaded
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        # assert upload.inbox_key is None
        # assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
        assert upload.filename == "file.zip"
        assert upload.completed_at
        # based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 70398
        assert upload.bucket_name == "private"
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == "https://s3.example.com"
        assert upload.skipped_keys == ["prefix/v0/flag/deadbeef/flag.jpeg"]
        assert upload.ignored_keys == ["build-symbols.txt"]

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload,
        bucket_name="private",
        key="prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


def test_key_existing_caching(botomock):

    user = FakeUser("peterbe@example.com")
    bucket_info = get_bucket_info(user)

    sizes_returned = []
    lookups = []

    def mock_api_call(self, operation_name, api_params):
        lookups.append((operation_name, api_params))

        if operation_name == "HeadObject" and api_params["Key"] == "filename":
            size = 1234
            if sizes_returned:
                size = 6789
            result = {"ContentLength": size}
            sizes_returned.append(size)
            return result

        raise NotImplementedError

    client = bucket_info.client
    with botomock(mock_api_call):
        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 1234
        assert metadata is None
        assert len(lookups) == 1

        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 1234
        assert metadata is None
        assert len(lookups) == 1

        key_existing.invalidate(client, "mybucket", "filename")
        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 6789
        assert metadata is None
        assert len(lookups) == 2


def test_key_existing_size_caching_not_found(botomock):

    user = FakeUser("peterbe@example.com")
    bucket_info = get_bucket_info(user)

    lookups = []

    def mock_api_call(self, operation_name, api_params):
        lookups.append((operation_name, api_params))

        if operation_name == "HeadObject" and api_params["Key"] == "filename":
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        raise NotImplementedError

    client = bucket_info.client
    with botomock(mock_api_call):
        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 0
        assert metadata is None
        assert len(lookups) == 1

        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 0
        assert metadata is None
        assert len(lookups) == 1

        key_existing.invalidate(client, "mybucket", "filename")
        size, metadata = key_existing(client, "mybucket", "filename")
        assert size == 0
        assert metadata is None
        assert len(lookups) == 2


@pytest.mark.django_db
def test_upload_archive_key_lookup_cached(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    lookups = []

    metadata_cache = {}

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Saying the size is 100 will cause the code to think the
            # symbol file *is different* so it'll proceed to upload it.
            size = 100
            if lookups:
                # If this is the second time, return the right size.
                size = 501
            result = {"ContentLength": size}
            if metadata_cache.get(api_params["Key"]):
                result["Metadata"] = metadata_cache[api_params["Key"]]
            lookups.append(size)
            return result

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            metadata_cache[api_params["Key"]] = api_params["Metadata"]
            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        assert FileUpload.objects.all().count() == 1

    # Upload the same file again. This time some of the S3 HeadObject
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 2
        assert FileUpload.objects.all().count() == 1
        assert len(lookups) == 2

    # Upload the same file again. This time some of the S3 HeadObject
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 3
        assert FileUpload.objects.all().count() == 1
        # This time it doesn't need to look up the size a third time
        assert len(lookups) == 2


@pytest.mark.django_db
def test_upload_archive_key_lookup_cached_without_metadata(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):
    """Same as test_upload_archive_key_lookup_cached() but without
    any metadata."""

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    lookups = []

    metadata_cache = {}

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Saying the size is 100 will cause the code to think the
            # symbol file *is different* so it'll proceed to upload it.
            size = 100
            if lookups:
                # If this is the second time, return the right size.
                size = 501
            result = {"ContentLength": size}
            if metadata_cache.get(api_params["Key"]):
                result["Metadata"] = metadata_cache[api_params["Key"]]
            lookups.append(size)
            return result

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        assert FileUpload.objects.all().count() == 1

    # Upload the same file again. This time some of the S3 HeadObject
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 2
        assert FileUpload.objects.all().count() == 1
        assert len(lookups) == 2

    # Upload the same file again. This time some of the S3 HeadObject
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 3
        assert FileUpload.objects.all().count() == 1
        # This time it doesn't need to look up the size a third time
        assert len(lookups) == 2


@pytest.mark.django_db
def test_upload_archive_key_lookup_cached_by_different_hashes(
    client,
    botomock,
    fakeuser,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    put_metadatas = []

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            return {
                "ContentLength": 501,  # Right!
                "Metadata": {
                    "original_size": 1156,  # Right!
                    "original_md5_hash": "notrightatall",  # Wrong!
                },
            }

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # ...pretend to actually upload it.
            put_metadatas.append(api_params["Metadata"])
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        # This is the important test. The size on S3 (after gzip) matches
        # this new incoming file. Also, the original file size also matches.
        # However, the S3 stored Metadata.original_md5_hash is different so
        # that it uploads the file.
        assert FileUpload.objects.all().count() == 1
        (file_upload,) = FileUpload.objects.all()
        assert file_upload.update

        (put_metadata,) = put_metadatas
        assert put_metadata["original_size"] == str(1156)
        assert put_metadata["original_md5_hash"] != "notrightatall"


@pytest.mark.django_db
def test_upload_archive_one_uploaded_one_errored(
    client, botomock, fakeuser, upload_mock_invalidate_symbolicate_cache
):
    class AnyUnrecognizedError(Exception):
        """Doesn't matter much what the exception is. What matters is that
        it happens during a boto call."""

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Not found at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            raise AnyUnrecognizedError("stop!")

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        with pytest.raises(AnyUnrecognizedError):
            client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        assert not upload.completed_at

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload, key="prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
    )


@pytest.mark.django_db
def test_upload_archive_with_cache_invalidation(
    client,
    botomock,
    fakeuser,
    settings,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):
    settings.SYMBOL_URLS = ["https://s3.example.com/mybucket"]
    settings.UPLOAD_DEFAULT_URL = "https://s3.example.com/mybucket"
    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    utils.downloader = downloader

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    # A mutable we use to help us distinguish between calls in the mock
    lookups = []

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "mybucket"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v0/flag/deadbeef/flag.jpeg"
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.

            return {"ContentLength": 1000}

        if operation_name == "ListObjectsV2" and api_params["Prefix"] == (
            "v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # This is when the SymbolDownloader queries it.
            result = {}
            if lookups:
                # Second time
                result = {"Contents": [{"Key": api_params["Prefix"], "Size": 100}]}
            lookups.append(api_params["Prefix"])
            return result

        if operation_name == "HeadObject" and api_params["Key"] == (
            "v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] == (
            "v0/flag/deadbeef/flag.jpeg"
        ):
            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }
        if operation_name == "PutObject" and api_params["Key"] == (
            "v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:

        assert not downloader.has_symbol(
            "xpcshell.dbg", "A7D6F1BB18CD4CB48", "xpcshell.sym"
        )

        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        # Second time.
        assert downloader.has_symbol(
            "xpcshell.dbg", "A7D6F1BB18CD4CB48", "xpcshell.sym"
        )

        # This is just basically to make sense of all the crazy mocking.
        assert len(lookups) == 2


@pytest.mark.django_db
def test_upload_archive_both_skipped(
    client, botomock, fakeuser, upload_mock_update_uploads_created_task
):

    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params["Bucket"] == "private"
        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            return {"ContentLength": 69183}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            return {"ContentLength": 501}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 201

        (upload,) = Upload.objects.all()
        assert upload.user == fakeuser
        assert upload.filename == "file.zip"
        assert upload.completed_at
        # based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 70398
        assert upload.bucket_name == "private"
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == "https://s3.example.com"
        # Order isn't predictable so compare using sets.
        assert set(upload.skipped_keys) == set(
            [
                "prefix/v0/flag/deadbeef/flag.jpeg",
                "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
            ]
        )
        assert upload.ignored_keys == ["build-symbols.txt"]

    assert not FileUpload.objects.all().exists()


@pytest.mark.django_db
def test_upload_archive_by_url(
    client,
    botomock,
    fakeuser,
    settings,
    requestsmock,
    upload_mock_invalidate_symbolicate_cache,
    upload_mock_update_uploads_created_task,
):

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )
    requestsmock.head(
        "https://whitelisted.example.com/bad.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://bad.example.com/symbols.zip"},
    )

    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = [
        "whitelisted.example.com",
        "download.example.com",
    ]
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    def mock_api_call(self, operation_name, api_params):
        assert api_params["Bucket"] == "private"

        if operation_name == "HeadBucket":
            # yep, bucket exists
            return {}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/flag/deadbeef/flag.jpeg"
        ):
            # file exists but wrong size, needs upload
            return {"ContentLength": 1000}

        if operation_name == "HeadObject" and api_params["Key"] == (
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym"
        ):
            # Not found at all
            parsed_response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        if operation_name == "PutObject" and api_params["Key"] in (
            "prefix/v0/flag/deadbeef/flag.jpeg",
            "prefix/v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym",
        ):
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, "rb") as f:
        response = client.post(
            url,
            data={"url": "http://example.com/symbols.zip"},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "Insecure URL"

        response = client.post(
            url,
            data={"url": "https://notwhitelisted.example.com/symbols.zip"},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 400
        assert response.json()["error"] == (
            "Not an allowed domain ('notwhitelisted.example.com') to " "download from."
        )

        # Lastly, the happy path
        zip_file_content = f.read()
        requestsmock.head(
            "https://download.example.com/symbols.zip",
            content=b"",
            status_code=200,
            headers={"Content-Length": str(len(zip_file_content))},
        )
        requestsmock.get(
            "https://whitelisted.example.com/symbols.zip",
            content=zip_file_content,
            status_code=200,
        )
        response = client.post(
            url,
            data={"url": "https://whitelisted.example.com/symbols.zip"},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201
        assert response.json()["upload"]["download_url"] == (
            "https://whitelisted.example.com/symbols.zip"
        )
        assert response.json()["upload"]["redirect_urls"] == [
            "https://download.example.com/symbols.zip"
        ]

        (upload,) = Upload.objects.all()
        assert upload.download_url
        assert upload.redirect_urls
        assert upload.user == fakeuser
        assert upload.filename == "symbols.zip"
        assert upload.completed_at

    assert FileUpload.objects.filter(upload=upload).count() == 2


@pytest.mark.django_db
def test_upload_archive_by_url_remote_error(client, fakeuser, settings, requestsmock):

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip", exc=ConnectionError
    )

    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")
    response = client.post(
        url,
        data={"url": "https://whitelisted.example.com/symbols.zip"},
        HTTP_AUTH_TOKEN=token.key,
    )
    assert response.status_code == 500
    assert response.json()["error"] == (
        "ConnectionError trying to open https://whitelisted.example.com/symbols.zip"
    )


@pytest.mark.django_db
def test_upload_client_bad_request(fakeuser, client, settings):

    url = reverse("upload:upload_archive")
    response = client.get(url)
    assert response.status_code == 405
    error_msg = "Method Not Allowed (GET): /upload/"
    assert response.json()["error"] == error_msg

    response = client.post(url)
    assert response.status_code == 403
    error_msg = "This requires an Auth-Token to authenticate the request"
    assert response.json()["error"] == error_msg

    token = Token.objects.create(user=fakeuser)
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


@pytest.mark.django_db
def test_upload_duplicate_files_in_zip_different_name(fakeuser, client):
    url = reverse("upload:upload_archive")
    token = Token.objects.create(user=fakeuser)
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


@pytest.mark.django_db
def test_upload_client_unrecognized_bucket(fakeuser, client):
    """The upload view raises an error if you try to upload into a bucket
    that doesn't exist."""
    token = Token.objects.create(user=fakeuser)
    (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    url = reverse("upload:upload_archive")

    with open(ZIP_FILE, "rb") as f, mock.patch(
        "tecken.storage.StorageBucket.exists", return_value=False
    ), pytest.raises(ImproperlyConfigured):
        client.post(url, {"file.zip": f}, HTTP_AUTH_TOKEN=token.key)


def test_get_bucket_info(settings):

    user = FakeUser("peterbe@example.com")

    settings.UPLOAD_DEFAULT_URL = "https://s3.amazonaws.com/some-bucket"
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "some-bucket"
    assert bucket_info.endpoint_url is None
    assert bucket_info.region is None
    assert not bucket_info.try_symbols

    settings.UPLOAD_DEFAULT_URL = "https://s3-eu-west-2.amazonaws.com/some-bucket"
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "some-bucket"
    assert bucket_info.endpoint_url is None
    assert bucket_info.region == "eu-west-2"

    settings.UPLOAD_DEFAULT_URL = "http://s3.example.com/buck/prefix"
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "buck"
    assert bucket_info.endpoint_url == "http://s3.example.com"
    assert bucket_info.region is None


def test_get_bucket_info_try_symbols(settings):

    user = FakeUser("peterbe@example.com", perms=("upload.upload_try_symbols",))

    settings.UPLOAD_DEFAULT_URL = "https://s3.amazonaws.com/some-bucket"
    settings.UPLOAD_TRY_SYMBOLS_URL = "https://s3.amazonaws.com/other-bucket"
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "other-bucket"
    assert bucket_info.endpoint_url is None
    assert bucket_info.region is None
    assert bucket_info.try_symbols

    # settings.UPLOAD_DEFAULT_URL = (
    #     'https://s3-eu-west-2.amazonaws.com/some-bucket'
    # )
    # bucket_info = get_bucket_info(user)
    # assert bucket_info.name == 'some-bucket'
    # assert bucket_info.endpoint_url is None
    # assert bucket_info.region == 'eu-west-2'
    #
    # settings.UPLOAD_DEFAULT_URL = 'http://s3.example.com/buck/prefix'
    # bucket_info = get_bucket_info(user)
    # assert bucket_info.name == 'buck'
    # assert bucket_info.endpoint_url == 'http://s3.example.com'
    # assert bucket_info.region is None


def test_get_bucket_info_exceptions(settings):

    settings.UPLOAD_DEFAULT_URL = "https://s3.amazonaws.com/buck"
    settings.UPLOAD_URL_EXCEPTIONS = {
        "peterbe@example.com": "https://s3.amazonaws.com/differenting",
        "t*@example.com": "https://s3.amazonaws.com/excepty",
    }

    user = FakeUser("Peterbe@example.com")
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "differenting"

    user = FakeUser("Tucker@example.com")
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == "excepty"


def test_get_bucket_info_preferred_bucket_name(settings):

    settings.UPLOAD_DEFAULT_URL = "https://s3.amazonaws.com/buck"
    settings.UPLOAD_URL_EXCEPTIONS = {
        "peterbe@example.com": "https://s3.amazonaws.com/differenting",
        "t*@example.com": "https://s3.amazonaws.com/excepty",
    }

    user = FakeUser("Peterbe@example.com")
    with pytest.raises(NoPossibleBucketName):
        get_bucket_info(user, preferred_bucket_name="neverheardof")

    user = FakeUser("Tucker@example.com")
    bucket_info = get_bucket_info(user, preferred_bucket_name="excepty")
    assert bucket_info.name == "excepty"

    user = FakeUser("Ted@example.com", is_superuser=True)
    bucket_info = get_bucket_info(user, preferred_bucket_name="excepty")
    assert bucket_info.name == "excepty"


def test_get_possible_bucket_urls(settings):

    settings.UPLOAD_DEFAULT_URL = "https://s3.amazonaws.com/buck"
    settings.UPLOAD_URL_EXCEPTIONS = {
        "peterbe@example.com": "https://s3.amazonaws.com/differenting",
        "t*@example.com": "https://s3.amazonaws.com/excepty",
    }
    user = FakeUser("Peterbe@example.com")
    urls = get_possible_bucket_urls(user)
    ((url, private_or_public),) = urls
    assert private_or_public == "private"
    assert url == "https://s3.amazonaws.com/differenting"

    user = FakeUser("Ted@example.com", is_superuser=True)
    urls = get_possible_bucket_urls(user)
    assert len(urls) == 3


def test_UploadByDownloadForm_happy_path(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip",
        content=b"content",
        status_code=200,
        headers={"Content-Length": "1234"},
    )

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    assert form.is_valid()
    assert form.cleaned_data["url"] == ("https://whitelisted.example.com/symbols.zip")
    assert form.cleaned_data["upload"]["name"] == "symbols.zip"
    assert form.cleaned_data["upload"]["size"] == 1234
    assert form.cleaned_data["upload"]["redirect_urls"] == []


def test_UploadByDownloadForm_redirects(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip",
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

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    assert form.is_valid()
    assert form.cleaned_data["url"] == ("https://whitelisted.example.com/symbols.zip")
    assert form.cleaned_data["upload"]["name"] == "symbols.zip"
    assert form.cleaned_data["upload"]["size"] == 1234
    assert form.cleaned_data["upload"]["redirect_urls"] == [
        "https://download.example.com/symbols.zip"
    ]


def test_UploadByDownloadForm_redirects_bad(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/symbols.zip"},
    )

    requestsmock.head(
        "https://download.example.com/symbols.zip",
        content=b"Internal Server Error",
        status_code=500,
    )

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()


def test_UploadByDownloadForm_connectionerrors(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip", exc=ConnectionError
    )

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()

    # Suppose the HEAD request goes to another URL which eventually
    # raises a ConnectionError.

    requestsmock.head(
        "https://whitelisted.example.com/redirect.zip",
        text="Found",
        status_code=302,
        headers={"Location": "https://download.example.com/busted.zip"},
    )
    requestsmock.head("https://download.example.com/busted.zip", exc=ConnectionError)
    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/redirect.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()

    # Suppose the URL simply is not found.
    requestsmock.head(
        "https://whitelisted.example.com/404.zip", text="Not Found", status_code=404
    )
    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/404.zip"})
    assert not form.is_valid()
    (validation_errors,) = form.errors.as_data().values()
    assert validation_errors[0].message == (
        "https://whitelisted.example.com/404.zip can't be found (404)"
    )


def test_UploadByDownloadForm_retryerror(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head("https://whitelisted.example.com/symbols.zip", exc=RetryError)

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    with pytest.raises(UploadByDownloadRemoteError):
        form.is_valid()


def test_UploadByDownloadForm_redirection_exhaustion(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ["whitelisted.example.com"]

    requestsmock.head(
        "https://whitelisted.example.com/symbols.zip",
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

    form = UploadByDownloadForm({"url": "https://whitelisted.example.com/symbols.zip"})
    assert not form.is_valid()
    (validation_errors,) = form.errors.as_data().values()
    assert "Too many redirects" in validation_errors[0].message


@pytest.mark.django_db
def test_update_uploads_created_task_empty():
    update_uploads_created_task()
    uploads_created = UploadsCreated.objects.all().get()
    assert uploads_created.date == timezone.now().date()
    assert uploads_created.count == 0
    assert uploads_created.files == 0
    assert uploads_created.skipped == 0
    assert uploads_created.ignored == 0
    assert uploads_created.size == 0
    assert uploads_created.size_avg == 0

    # Just to be sure, execute again and nothing should change.
    update_uploads_created_task()
    assert UploadsCreated.objects.all().count() == 1


@pytest.mark.django_db
def test_uploads_created_update():
    today = timezone.now().date()
    instance = UploadsCreated.update(today)
    assert instance.date == today
    assert instance.count == 0

    user = User.objects.create(email="her@example.com")
    for i in range(10):
        upload = Upload.objects.create(
            user=user,
            # Make it a huge number to make sure it's (when x10) bigger than
            # the max size of a regular 'integer' in postgres.
            size=250_000_000,
            skipped_keys=["foo"],
            ignored_keys=["bar"],
        )
        FileUpload.objects.create(upload=upload, size=123_499, key="foo.sym")

    old_instance = instance
    instance = UploadsCreated.update(today)
    assert old_instance.id == instance.id
    assert instance.date == today
    assert instance.count == 10
    assert instance.size == 2_500_000_000
