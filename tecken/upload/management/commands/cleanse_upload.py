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

    def delete_records(self, is_try, cutoff):
        uploads = Upload.objects.filter(try_symbols=is_try, created_at__lte=cutoff)
        ret = FileUpload.objects.filter(upload__in=uploads).delete()
        self.stdout.write(
            f"cleanse_upload: fileupload try={is_try}: Deleted {ret[0]} records older than {cutoff}"
        )
        ret = uploads.delete()
        self.stdout.write(
            f"cleanse_upload: upload try={is_try}: Deleted {ret[0]} records older than {cutoff}"
        )

    def handle(self, *args, **options):
        today = timezone.now()

        # First cleanse try records
        try_cutoff = today - datetime.timedelta(days=TRY_RECORD_AGE_CUTOFF)
        self.delete_records(is_try=True, cutoff=try_cutoff)

        # Now cleanse regular records
        cutoff = today - datetime.timedelta(days=REGULAR_RECORD_AGE_CUTOFF)
        self.delete_records(is_try=False, cutoff=cutoff)
