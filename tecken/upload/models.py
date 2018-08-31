# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import datetime

from django.db import models
from django.conf import settings
from django.db.models import Aggregate, Count, Sum, Avg
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.template.defaultfilters import filesizeformat


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
    size = models.PositiveIntegerField()
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

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} id={self.id} "
            f"filename={self.filename!r} "
            f"bucket_name={self.bucket_name!r}"
            f">"
        )


class FileUpload(models.Model):
    """
    Each Upload is a .zip file containing other files. Each of those
    files are uploaded individually to the same bucket.
    """

    upload = models.ForeignKey(Upload, null=True, on_delete=models.SET_NULL)
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
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} bucket_name={self.bucket_name!r} "
            f"key={self.key!r} size={self.size}>"
        )


class UploadsCreated(models.Model):
    """Count of the number of Uploads per day."""

    # Always in UTC
    date = models.DateField(db_index=True, unique=True)
    count = models.PositiveIntegerField()
    files = models.PositiveIntegerField()
    skipped = models.PositiveIntegerField()
    ignored = models.PositiveIntegerField()
    size = models.BigIntegerField()
    size_avg = models.PositiveIntegerField()
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} date={self.date} "
            f"count={format(self.count, ',')} "
            f"files={format(self.files, ',')} "
            f"skipped={format(self.skipped, ',')} "
            f"ignored={format(self.ignored, ',')} "
            f"size={filesizeformat(self.size)}>"
        )

    @classmethod
    def update(cls, date):
        assert isinstance(date, datetime.date), type(date)
        date_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.datetime.min.time())
        )
        qs = Upload.objects.filter(
            created_at__gte=date_datetime,
            created_at__lt=date_datetime + datetime.timedelta(days=1),
        )
        aggregates_numbers = qs.aggregate(
            count=Count("id"),
            size_avg=Avg("size"),
            size_sum=Sum("size"),
            skipped_sum=SumCardinality("skipped_keys"),
            ignored_sum=SumCardinality("ignored_keys"),
        )
        file_uploads_qs = FileUpload.objects.filter(upload__in=qs)
        files = file_uploads_qs.count()

        count = aggregates_numbers["count"]
        skipped = aggregates_numbers["skipped_sum"] or 0
        ignored = aggregates_numbers["ignored_sum"] or 0
        size = aggregates_numbers["size_sum"] or 0
        size_avg = (
            aggregates_numbers["size_avg"] and int(aggregates_numbers["size_avg"]) or 0
        )
        # XXX Can we just use update_or_create?? Probably wait till Django 2.1.1
        if cls.objects.filter(date=date).exists():
            # Update!
            cls.objects.filter(date=date).update(
                date=date,
                count=count,
                files=files,
                skipped=skipped,
                ignored=ignored,
                size=size,
                size_avg=size_avg,
            )
            return cls.objects.get(date=date)
        else:
            return cls.objects.create(
                date=date,
                count=count,
                files=files,
                skipped=skipped,
                ignored=ignored,
                size=size,
                size_avg=size_avg,
            )
