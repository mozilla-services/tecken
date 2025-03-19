# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.core.management import call_command
from django.core.management.base import BaseCommand

from tecken.libmarkus import METRICS


class Command(BaseCommand):
    """Clean out stale data from the database.

    This runs the following management commands:

    * remove_stale_contenttypes
    * clearsessions - remove expired sessions
    * clearuploads - remove database records for expired uploads
    """

    help = "Clean out stale data from the database."

    def handle(self, *args, **options):
        # Remove stale contenttypes
        self.stdout.write(">>> running remove_stale_contenttypes")
        with METRICS.timer("cleanup.clearsessions_timing"):
            call_command("clearsessions")

        # Clear expired sessions
        self.stdout.write("\n>>> running clearsessions")
        with METRICS.timer("cleanup.remove_stale_contenttypes_timing"):
            call_command("remove_stale_contenttypes")

        # Clear expired upload and fileupload records
        self.stdout.write("\n>>> running clearuploads")
        call_command("clearuploads")
