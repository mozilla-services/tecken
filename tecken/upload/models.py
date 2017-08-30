# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField


class Upload(models.Model):
    """
    Record of every uploaded archive file (e.g. .zip) that is uploaded,
    then placed in S3 and then, as a background task, processed such
    that each file within is uploaded to the right destination.

    Note that, which bucket to upload depends on which user uploaded.
    This is a paradigm that might change over time since some same user
    might have explicit preferences where she wants the symbols stored.

    The primary use case for using different buckets is security. Some
    symbols should be publicly available, others not.
    """
    # Who uploaded it
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    # The filename it was called when uploaded as an archive
    filename = models.CharField(max_length=100)
    # The name of the bucket where it was placed temporarily
    bucket_name = models.CharField(max_length=100)
    bucket_region = models.CharField(max_length=100, null=True)
    bucket_endpoint_url = models.CharField(max_length=100, null=True)
    # S3 key name to the temporary upload
    inbox_key = models.CharField(max_length=300)
    # When the archive contains keys we decide NOT to upload
    skipped_keys = ArrayField(models.CharField(max_length=300), null=True)
    # When certain files are immediately ignored
    ignored_keys = ArrayField(models.CharField(max_length=300), null=True)
    # When the upload has been extracted and all individual files
    # have been successfully uploaded, this is complete.
    completed_at = models.DateTimeField(null=True)
    size = models.PositiveIntegerField()
    # If the upload was by a download URL
    download_url = models.URLField(max_length=500, null=True)
    # One increment for every attempt of processing the upload.
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        permissions = (
            ('upload_symbols', 'Upload Symbols Files'),
            ('view_all_uploads', 'View All Symbols Uploads'),
        )

    def __repr__(self):
        return (
            f'<{self.__class__.__name__} id={self.id} '
            f'filename={self.filename!r} '
            f'bucket_name={self.bucket_name!r} inbox_key={self.inbox_key!r}>'
        )


class FileUpload(models.Model):
    """
    Each Upload is a .zip file containing other files. Each of those
    files are uploaded individually to the same bucket.

    NOTE! Generally these objects are created in bulk.
    """
    upload = models.ForeignKey(Upload, null=True)
    bucket_name = models.CharField(max_length=100)
    key = models.CharField(max_length=300)
    # True if this overwrote an existing key
    update = models.BooleanField(default=False)
    # True if the file was gzip compressed before being uploaded
    compressed = models.BooleanField(default=False)
    size = models.PositiveIntegerField()
    # Used when this upload belongs to a Microsoft proxy download
    microsoft_download = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f'<{self.__class__.__name__} bucket_name={self.bucket_name!r} '
            f'key={self.key!r} size={self.size}>'
        )
