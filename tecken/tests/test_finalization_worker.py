# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Literal

from django.contrib.auth.models import User
from django.utils import timezone
import pytest

from tecken.libstorage import Notification, ObjectMetadata
from tecken.upload.management.commands.finalization_worker import _process_notification
from tecken.upload.models import FileUpload, Upload


@pytest.mark.parametrize("event_type", ["finalize_new", "finalize_update"])
@pytest.mark.django_db
def test_process_notification(
    fakeuser: User, event_type: Literal["finalize_new", "finalize_update"]
):
    upload = Upload.objects.create(
        user=fakeuser,
        size=200,
        outstanding_file_uploads=2,
        bucket_name="publicbucket",
    )

    # Send notifications for two uploaded files.
    for i, key in enumerate(["a/b/c", "d/e/f"]):
        metadata = ObjectMetadata(
            content_length=100,
            download_url=f"http://localhost:8000/{key}",
            upload_id=upload.id,
        )
        notification = Notification(
            event_type=event_type,
            event_time=timezone.now(),
            key=key,
            metadata=metadata,
        )

        # Process each notification twice to test idempotency.
        for _dummy in range(2):
            _process_notification(notification)

            file_upload = FileUpload.objects.get(upload=upload, key=key)
            assert file_upload.completed_at == notification.event_time
            assert file_upload.bucket_name == upload.bucket_name
            if event_type == "finalize_new":
                assert not file_upload.update
            else:
                assert file_upload.update
            assert not file_upload.compressed
            assert file_upload.size == metadata.content_length

            upload.refresh_from_db()
            assert upload.outstanding_file_uploads == 1 - i

    # After uploading all outstanding files, completed_at should be set.
    assert upload.completed_at is not None
