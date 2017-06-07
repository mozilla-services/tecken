from django.db import models
from django.conf import settings


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
    # When the upload has been extracted and all individual files
    # have been successfully uploaded, this is complete.
    completed_at = models.DateTimeField(null=True)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __repr__(self):
        return '<{} filename={!r} bucket_name={!r} inbox_key={!r}>'.format(
            self.__class__.__name__,
            self.filename,
            self.bucket_name,
            self.inbox_key,
        )


class FileUpload(models.Model):
    """
    Each Upload is a .zip file containing other files. Each of those
    files are uploaded individually to the same bucket.

    NOTE! Generally these objects are created in bulk.
    """
    upload = models.ForeignKey(Upload)
    bucket_name = models.CharField(max_length=100)
    key = models.CharField(max_length=300)
    # True if this overwrote an existing key
    update = models.BooleanField(default=False)
    # True if the file was gzip compressed before being uploaded
    compressed = models.BooleanField(default=False)
    size = models.PositiveIntegerField()
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
