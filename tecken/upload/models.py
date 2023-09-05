# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django.conf import settings
from django.db.models import Aggregate
from django.contrib.postgres.fields import ArrayField


class SumCardinality(Aggregate):
    template = "SUM(CARDINALITY(%(expressions)s))"


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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # The filename it was called when uploaded as an archive
    filename = models.CharField(max_length=100)
    # The name of the bucket where it was placed temporarily
    bucket_name = models.CharField(max_length=100)
    bucket_region = models.CharField(max_length=100, null=True)
    bucket_endpoint_url = models.CharField(max_length=100, null=True)
    # When the archive contains keys we decide NOT to upload
    skipped_keys = ArrayField(models.CharField(max_length=300), null=True)
    # When certain files are immediately ignored
    ignored_keys = ArrayField(models.CharField(max_length=300), null=True)
    # When the upload has been extracted and all individual files
    # have been successfully uploaded, this is complete.
    completed_at = models.DateTimeField(null=True)
    size = models.PositiveBigIntegerField()
    content_hash = models.CharField(null=True, max_length=32)
    # If the upload was by a download URL
    download_url = models.URLField(max_length=500, null=True)
    # If the uploaded symbols come from a Try build.
    try_symbols = models.BooleanField(default=False)
    # If the upload by download URL triggered 1 or more redirects, we
    # record that trail here.
    redirect_urls = ArrayField(models.URLField(max_length=500), null=True)
    # One increment for every attempt of processing the upload.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        permissions = (
            ("upload_symbols", "Upload Symbols Files"),
            ("upload_try_symbols", "Upload Try Symbols Files"),
            ("view_all_uploads", "View All Symbols Uploads"),
        )

    def __str__(self):
        return (
            "<"
            + f"{self.__class__.__name__}:{self.id} "
            + f"bucket_name={self.bucket_name!r} "
            + f"filename={self.filename!r} "
            + f"size={self.size!r} "
            + f"created_at={self.created_at!r}"
            + ">"
        )

    def get_absolute_url(self):
        # NOTE(willkg): This is a React url. This will fail in local development because
        # Django webapp runs at port 8000, but the React webapp runs at port 3000.
        return f"/uploads/upload/{self.id}"


class FileUpload(models.Model):
    """
    Each Upload is a .zip file containing other files. Each of those
    files are uploaded individually to the same bucket.
    """

    # NOTE(willkg): we use SET_NULL here because this table and the FileUpload tables
    # are really big so deleting things with CASCADE gets rough; at some point when we
    # have more time for deleting things and it's done regularly, we should set this to
    # CASCADE.
    upload = models.ForeignKey(Upload, null=True, on_delete=models.SET_NULL)
    bucket_name = models.CharField(max_length=100)
    key = models.CharField(max_length=300)
    # True if this overwrote an existing key
    update = models.BooleanField(default=False)
    # True if the file was gzip compressed before being uploaded
    compressed = models.BooleanField(default=False)
    size = models.PositiveIntegerField()
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # NOTE(willkg): This used to be used when this upload belongs to a Microsoft proxy
    # download, but that code was removed, so now this does nothing and can be removed.
    microsoft_download = models.BooleanField(default=False)

    def __str__(self):
        return (
            "<"
            + f"{self.__class__.__name__}:{self.id} "
            + f"bucket_name={self.bucket_name!r} "
            + f"key={self.key!r} "
            + f"size={self.size} "
            + f"created_at={self.created_at}"
            + ">"
        )

    def get_absolute_url(self):
        # NOTE(willkg): This is a React url. This will fail in local development because
        # Django webapp runs at port 8000, but the React webapp runs at port 3000.
        return f"/uploads/files/file/{self.id}"
