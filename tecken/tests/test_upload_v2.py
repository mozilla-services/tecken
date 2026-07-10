# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from hashlib import md5
from typing import Any

from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from markus.testing import AnyTagValue, MetricsMock
import msgspec
import pytest
from pytest_django.fixtures import SettingsWrapper

from tecken.base.symbolstorage import SymbolStorage
from tecken.tests.utils import UPLOADS
from tecken.tokens.models import Token
from tecken.upload.views import FileSpecRequest, UploadRequest


def perform_uploads(
    client: Client, token: Token, file_specs: list[FileSpecRequest]
) -> dict[str, Any]:
    """Perform an upload v2 request using the Django test client."""
    response = client.post(
        reverse("upload:upload_v2"),
        data=msgspec.json.encode(UploadRequest(files=file_specs)),
        content_type="application/json",
        headers={"Auth-Token": token.key},
    )
    assert response.status_code == 201
    return response.json()


def create_token(user: User, try_storage: bool) -> Token:
    """Create an upload token for the given user."""
    token = Token.objects.create(user=user)
    if try_storage:
        (permission,) = Permission.objects.filter(codename="upload_try_symbols")
    else:
        (permission,) = Permission.objects.filter(codename="upload_symbols")
    token.permissions.add(permission)
    return token


def assert_timing_count(metricsmock: MetricsMock, stat: str, count: int):
    """Assert the given number of timing records were emitted for the given metric."""
    assert (
        len(
            metricsmock.filter_records(
                "timing", stat=f"tecken.{stat}", tags=["host:testnode"]
            )
        )
        == count
    )


def assert_incr_count(
    metricsmock: MetricsMock,
    stat: str,
    count: int,
    tags: list[str | AnyTagValue] | None = None,
):
    """Assert the given number of incr records were emitted for the given metric."""
    tags = tags or []
    tags.append("host:testnode")
    assert (
        len(
            metricsmock.filter_records(
                "incr", stat=f"tecken.{stat}", value=1, tags=tags
            )
        )
        == count
    )


@pytest.mark.parametrize("try_storage", [False, True])
@pytest.mark.django_db
def test_upload_v2(
    client: Client,
    uploaderuser: User,
    symbol_storage: SymbolStorage,
    metricsmock: MetricsMock,
    try_storage: bool,
):
    token = create_token(uploaderuser, try_storage)

    file_specs = [u.file_spec() for u in UPLOADS.values()]
    upload_response = perform_uploads(client, token, file_specs)
    assert upload_response["try_symbols"] is try_storage
    assert upload_response["upload_protocol"] == "gcs-resumable"
    assert upload_response["user"] == uploaderuser.email
    for upload, file_spec in zip(
        UPLOADS.values(), upload_response["files"], strict=True
    ):
        assert file_spec["key"] == upload.key
        action = file_spec["action"]
        assert action["type"] == "upload"
        assert action.get("content_encoding") == upload.metadata.content_encoding
        assert action["url"].startswith("http://gcs-emulator:")

    assert_timing_count(metricsmock, "upload_v2", 1)
    assert_timing_count(metricsmock, "initiate_file_upload", len(UPLOADS))
    assert_timing_count(metricsmock, "upload_file_exists", len(UPLOADS))
    assert_incr_count(
        metricsmock,
        "upload_uploads",
        1,
        tags=[f"try:{try_storage}", AnyTagValue("bucket")],
    )
    assert_incr_count(
        metricsmock,
        "upload_uploads",
        0,
        tags=[f"try:{not try_storage}", AnyTagValue("bucket")],
    )
    assert_incr_count(metricsmock, "upload_file_upload_error", 0)
    assert_incr_count(metricsmock, "upload_file_upload_skip", 0)
    assert_incr_count(metricsmock, "upload_file_upload_upload", len(UPLOADS))


@pytest.mark.parametrize("try_storage", [False, True])
@pytest.mark.django_db
def test_upload_v2_skips(
    client: Client,
    uploaderuser: User,
    symbol_storage: SymbolStorage,
    metricsmock: MetricsMock,
    try_storage: bool,
):
    token = create_token(uploaderuser, try_storage)

    # Make all uploads available in symbol storage, so they will be skipped during the
    # upload request.
    for upload in UPLOADS.values():
        upload.upload(symbol_storage)

    file_specs = [u.file_spec() for u in UPLOADS.values()]
    upload_response = perform_uploads(client, token, file_specs)
    assert upload_response["try_symbols"] is try_storage
    assert upload_response["upload_protocol"] == "gcs-resumable"
    assert upload_response["user"] == uploaderuser.email
    for upload, file_spec in zip(
        UPLOADS.values(), upload_response["files"], strict=True
    ):
        assert file_spec["key"] == upload.key
        assert file_spec["action"]["type"] == "skip"

    assert_timing_count(metricsmock, "upload_v2", 1)
    assert_timing_count(metricsmock, "initiate_file_upload", len(UPLOADS))
    assert_timing_count(metricsmock, "upload_file_exists", len(UPLOADS))
    assert_incr_count(
        metricsmock,
        "upload_uploads",
        1,
        tags=[f"try:{try_storage}", AnyTagValue("bucket")],
    )
    assert_incr_count(
        metricsmock,
        "upload_uploads",
        0,
        tags=[f"try:{not try_storage}", AnyTagValue("bucket")],
    )
    assert_incr_count(metricsmock, "upload_file_upload_error", 0)
    assert_incr_count(metricsmock, "upload_file_upload_skip", len(UPLOADS))
    assert_incr_count(metricsmock, "upload_file_upload_upload", 0)


@pytest.mark.django_db
def test_upload_v2_errors(client: Client, uploaderuser: User, metricsmock: MetricsMock):
    token = create_token(uploaderuser, False)

    invalid_keys = [
        "xül.pdb/1A2B3C4/xul.sym",  # <-- note the extended ascii char
        "x%l.pdb/1A2B3C4/xul.sym",  # <-- note the %
        "xul.pdb/1A2B3C/xul#.ex_",  # <-- note the #
        "xul.so/1A2B3G4E/xul.sym",  # <-- note the G in the debug id
        "crypt3\x10.pdb/1A2B3C/crypt3\x10.pd_",
    ]
    invalid_md5_hashes = {
        "xul.pdb/1/xul.sym": "D41D8CD98F00B204E9800998ECF8427E",  # only lowercase hex digits are allowed
        "xul.pdb/2/xul.sym": "d41d8cd98f00b204e9800998ecf8427",  # too short
        "xul.pdb/3/xul.sym": "d41d8cd98f00b204e9800998ecf8427e1",  # too long
    }
    valid_md5_hash = md5(b"").hexdigest()
    file_specs = [
        FileSpecRequest(key, size=5, md5_hash=valid_md5_hash) for key in invalid_keys
    ] + [
        FileSpecRequest(key, size=5, md5_hash=md5_hash)
        for key, md5_hash in invalid_md5_hashes.items()
    ]
    expected_errors = ["invalid key"] * len(invalid_keys) + [
        "invalid MD5 hex digest"
    ] * len(invalid_md5_hashes)
    upload_response = perform_uploads(client, token, file_specs)
    assert upload_response["try_symbols"] is False
    assert upload_response["upload_protocol"] == "gcs-resumable"
    assert upload_response["user"] == uploaderuser.email
    for file_spec_req, file_spec, expected_error in zip(
        file_specs, upload_response["files"], expected_errors, strict=True
    ):
        assert file_spec["key"] == file_spec_req.key
        assert file_spec["action"]["type"] == "error"
        assert file_spec["action"]["msg"] == expected_error

    assert_timing_count(metricsmock, "upload_v2", 1)
    assert_timing_count(metricsmock, "initiate_file_upload", len(file_specs))
    assert_timing_count(metricsmock, "upload_file_exists", 0)
    assert_incr_count(
        metricsmock,
        "upload_uploads",
        1,
        tags=["try:False", "bucket:publicbucket"],
    )
    assert_incr_count(metricsmock, "upload_file_upload_error", len(file_specs))
    assert_incr_count(metricsmock, "upload_file_upload_skip", 0)
    assert_incr_count(metricsmock, "upload_file_upload_upload", 0)


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b'{"files": "wrong type"}',
        b'{"files": [{"key": "missing_md5_hash", size: 123}]}',
        b'{"files": [{"key": "a/b/c", size: 123, md5_hash: "abc", "surplus": "property"}]}',
    ],
)
def test_upload_v2_invalid_body(client: Client, uploaderuser: User, body: bytes):
    token = create_token(uploaderuser, False)
    response = client.post(
        reverse("upload:upload_v2"),
        data=body,
        content_type="application/json",
        headers={"Auth-Token": token.key},
    )
    assert response.status_code == 400
    error_response = response.json()
    assert error_response["error"] == "malformed JSON request body"


def test_upload_v2_too_many_files(
    client: Client, uploaderuser: User, settings: SettingsWrapper
):
    token = create_token(uploaderuser, False)
    settings.UPLOAD_V2_MAX_FILES_PER_REQUEST = len(UPLOADS) - 1
    file_specs = [u.file_spec() for u in UPLOADS.values()]
    response = client.post(
        reverse("upload:upload_v2"),
        data=msgspec.json.encode(UploadRequest(files=file_specs)),
        content_type="application/json",
        headers={"Auth-Token": token.key},
    )
    assert response.status_code == 400
    error_response = response.json()
    assert error_response["error"] == "too many files"
