# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import base64
import binascii

from tecken.libstorage import ObjectMetadata


def build_object_metadata(
    size: int | None, md5_hash: str, gcs_metadata: dict[str, str]
) -> ObjectMetadata:
    """Helper function to build an ObjectMetadata instance from information provided by GCS.

    This is used both in GcsStorage.get_object_metadata() and GoogleNotificationQueue.subscribe(),
    so it's factored out here.
    """
    original_content_length = gcs_metadata.get("original_size")
    if original_content_length is None:
        original_content_length = size
    else:
        try:
            original_content_length = int(original_content_length)
        except ValueError:
            original_content_length = None
    original_md5_sum = gcs_metadata.get("original_md5_hash")
    if original_md5_sum is None:
        try:
            original_md5_sum = base64.b64decode(md5_hash).hex()
        except binascii.Error:
            pass
    upload_id = gcs_metadata.get("upload_id")
    if upload_id is not None:
        try:
            upload_id = int(upload_id)
        except ValueError:
            upload_id = None
    metadata = ObjectMetadata(
        content_length=size,
        original_content_length=original_content_length,
        original_md5_sum=original_md5_sum,
        upload_id=upload_id,
    )
    return metadata
