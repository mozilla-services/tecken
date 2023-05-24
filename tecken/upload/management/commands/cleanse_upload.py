# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime

from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from django.utils import timezone

from tecken.libtiming import record_timing
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

        if is_dry_run:
            fileupload_count = file_uploads.count()
            upload_count = uploads.count()

        else:
            # NOTE(willkg): We use ._raw_delete() instead of .delete() here because
            # .delete() causes a SELECT which pulls back all the data of the stuff to be
            # deleted which is really intense and makes it not possible to run these
            # queries in prod. It does that to prevent an integrity error because
            # FileUpload has on_delete SET_NULL.
            #
            # We make sure to delete FileUpload before Upload, to prevent the integrity
            # error.

            del_query = file_uploads._chain()
            fileupload_count = file_uploads._raw_delete(using=del_query.db)

            del_query = uploads._chain()
            upload_count = uploads._raw_delete(using=del_query.db)

        self.stdout.write(
            f">>> try={is_try}, cutoff={cutoff.date()}: "
            + f"deleted upload={upload_count}, fileupload={fileupload_count}"
        )

    def handle(self, *args, **options):
        self.stdout.write("cleanse_upload:")

        # NOTE(willkg): if DEBUG=False, there's nothing to reset and this is a no-op
        reset_queries()

        is_dry_run = options["dry_run"]
        today = timezone.now()
        today.replace(hour=0, minute=0, second=0, microsecond=0)

        if is_dry_run:
            self.stdout.write(">>> THIS IS A DRY RUN.")

        with record_timing("count", self.stdout):
            upload_count = Upload.objects.all().count()
            fileupload_count = FileUpload.objects.all().count()
            self.stdout.write(
                ">>> count before cleansing: "
                + f"upload={upload_count}, fileupload={fileupload_count}"
            )

        with record_timing("delete", self.stdout):
            # First cleanse try records
            try_cutoff = today - datetime.timedelta(days=TRY_RECORD_AGE_CUTOFF)
            self.delete_records(is_dry_run=is_dry_run, is_try=True, cutoff=try_cutoff)

        with record_timing("delete", self.stdout):
            # Now cleanse regular records
            cutoff = today - datetime.timedelta(days=REGULAR_RECORD_AGE_CUTOFF)
            self.delete_records(is_dry_run=is_dry_run, is_try=False, cutoff=cutoff)

        # NOTE(willkg): this only prints the SQL when DEBUG=True
        for query in connection.queries:
            self.stdout.write(f"{query}")
