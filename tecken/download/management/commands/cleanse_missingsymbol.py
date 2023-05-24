# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tecken.download.models import MissingSymbol
from tecken.libtiming import record_timing


# Number of days to keep records--anything with a modified older than this will
# get deleted.
RECORD_AGE_CUTOFF = 30


class Command(BaseCommand):
    """Periodic maintenance task for deleting old missing symbol records.

    If we haven't updated a missing symbol record in over RECORD_AGE_CUTOFF
    days, then it's either that no one is looking for that symbol or that the
    file isn't missing anymore. In either case, we don't need to keep track of
    it anymore.

    """

    help = "Cleanse the downloads_missingsymbol table of impurities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Whether or not to do a dry run."
        )

    def handle(self, *args, **options):
        self.stdout.write("cleanse_missingsymbol:")
        is_dry_run = options["dry_run"]
        today = timezone.now()
        today.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today - datetime.timedelta(days=RECORD_AGE_CUTOFF)

        if is_dry_run:
            self.stdout.write(">>> THIS IS A DRY RUN.")

        with record_timing("count", self.stdout):
            total_count = MissingSymbol.objects.all().count()
            self.stdout.write(
                f">>> count before cleansing: missingsymbol={total_count}"
            )

        with record_timing("delete", self.stdout):
            syms = MissingSymbol.objects.filter(modified_at__lte=cutoff)
            if is_dry_run:
                count = syms.count()
            else:
                count = syms.delete()[0]

            self.stdout.write(
                f">>> cutoff={cutoff.date()}: deleted missingsymbol={count}"
            )
