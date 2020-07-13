# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tecken.upload.models import Upload, FileUpload


# Number of days to keep records--anything with a modified older than this will
# get deleted. These should match (close-enough) the expiration settings on
# the related S3 buckets.
TRY_RECORD_AGE_CUTOFF = 30
REGULAR_RECORD_AGE_CUTOFF = 365 * 2


class Command(BaseCommand):
    """Periodic maintenance task for deleting old upload records.

    The S3 buckets expire old objects, so we should expire the related records
    in these tables as well.

    """

    help = "Cleanse the upload_upload and upload_fileupload table of impurities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Whether or not to do a dry run."
        )

    def delete_records(self, is_dry_run, is_try, cutoff):
        uploads = Upload.objects.filter(try_symbols=is_try, created_at__lte=cutoff)
        file_uploads = FileUpload.objects.filter(upload__in=uploads)

        # Delete fileupload first because it's got a foreignkey to upload
        if is_dry_run:
            fileupload_count = file_uploads.count()
        else:
            fileupload_count = file_uploads.delete()[0]

        if is_dry_run:
            upload_count = uploads.count()
        else:
            upload_count = uploads.delete()[0]

        self.stdout.write(
            f"cleanse_upload: try={is_try}, cutoff={cutoff.date()}: "
            f"deleted upload={upload_count}, fileupload={fileupload_count}"
        )

    def handle(self, *args, **options):
        is_dry_run = options["dry_run"]
        today = timezone.now()
        today.replace(hour=0, minute=0, second=0, microsecond=0)

        if is_dry_run:
            self.stdout.write("cleanse_upload: THIS IS A DRY RUN.")

        upload_count = Upload.objects.all().count()
        fileupload_count = FileUpload.objects.all().count()
        self.stdout.write(
            f"cleanse_upload: count before cleansing: "
            f"upload={upload_count}, fileupload={fileupload_count}"
        )

        # First cleanse try records
        try_cutoff = today - datetime.timedelta(days=TRY_RECORD_AGE_CUTOFF)
        self.delete_records(is_dry_run=is_dry_run, is_try=True, cutoff=try_cutoff)

        # Now cleanse regular records
        cutoff = today - datetime.timedelta(days=REGULAR_RECORD_AGE_CUTOFF)
        self.delete_records(is_dry_run=is_dry_run, is_try=False, cutoff=cutoff)
