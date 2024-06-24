# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.conf import settings
from django.db import models
from django.contrib.postgres.fields import ArrayField


logger = logging.getLogger("tecken")


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


class FileUploadManager(models.Manager):
    def lookup_by_syminfo(self, some_file, some_id):
        """Returns a queryset filtering on debug_filename/debug_id or code_file/code_id combo

        :arg some_file: either a debug_filename (e.g. "xul.pdb") or a code_file (e.g. "xul.dll")
        :arg some_id: either a debug_id or a code_id

        :returns: queryset or None

        """
        logger.debug(f"lookup by some file={some_file!r} some_id={some_id!r}")
        return self.filter(
            (models.Q(debug_filename=some_file) & models.Q(debug_id=some_id))
            | (models.Q(code_file=some_file) & models.Q(code_id=some_id))
        ).order_by()


class FileUpload(models.Model):
    """
    Each Upload is a .zip file containing other files. Each of those
    files are uploaded individually to the same bucket.
    """

    class Meta:
        indexes = [
            models.Index(
                name="upload_fileupload_debuginfo",
                fields=["debug_filename", "debug_id"],
                condition=(
                    models.Q(debug_filename__isnull=False)
                    & models.Q(debug_id__isnull=False)
                ),
            ),
            models.Index(
                name="upload_fileupload_codeinfo",
                fields=["code_file", "code_id"],
                condition=(
                    models.Q(code_file__isnull=False) & models.Q(code_id__isnull=False)
                ),
            ),
        ]

    objects = FileUploadManager()

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

    # For sym files, these are generated during the build process. We track them because
    # they're helpful for debugging and lookups by code_id.
    debug_filename = models.TextField(
        null=True,
        blank=True,
        help_text=(
            "The debug filename for the symbol file generated at build time. Examples: "
            + "libmozsqlite3.so, xul.pdb. (sym)"
        ),
    )
    debug_id = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="The debug id for the symbol file generated at build time. (sym)",
    )
    code_file = models.TextField(
        null=True, blank=True, help_text="The module code file. (sym, Windows)"
    )
    code_id = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="The module code id. (sym, Windows)",
    )
    generator = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="The tool that generated the sym file. (sym)",
    )

    def __str__(self):
        return (
            "<"
            + f"{self.__class__.__name__}:{self.id} "
            + f"bucket_name={self.bucket_name!r} "
            + f"key={self.key!r} "
            + f"size={self.size!r} "
            + f"created_at={self.created_at!r}"
            + ">"
        )

    def get_absolute_url(self):
        # NOTE(willkg): This is a React url. This will fail in local development because
        # Django webapp runs at port 8000, but the React webapp runs at port 3000.
        return f"/uploads/files/file/{self.id}"
