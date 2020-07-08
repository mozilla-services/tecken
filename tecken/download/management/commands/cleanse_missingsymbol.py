# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tecken.download.models import MissingSymbol


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

    def handle(self, *args, **options):
        today = timezone.now()
        cutoff = today - datetime.timedelta(days=RECORD_AGE_CUTOFF)

        ret = MissingSymbol.objects.filter(modified_at__lte=cutoff).delete()
        self.stdout.write(
            f"cleanse_missingsymbol: Deleted {ret[0]} records older than {cutoff}."
        )
