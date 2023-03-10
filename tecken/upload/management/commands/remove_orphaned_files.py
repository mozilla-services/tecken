# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand

import markus

metrics = markus.get_metrics("tecken")


SLEEP_TIME = 5 * 60


class Command(BaseCommand):
    help = "Watch upload_tempdir directory for orphaned files and delete them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--daemon", action="store_true", help="Whether to run as a daemon or not."
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Whether to run verbosely."
        )

    def delete_orphans(self, watchdir, expires):
        """Delete orphaned files

        Note: This does not delete empty directories. It's hard to figure out which
        directories are from orphaned files and which ones aren't and the consequences
        of making a mistake will break a symbol uploading job. Orphaned files happen
        rarely, so empty directories shouldn't stack up. We can implement this if any of
        those things change.

        :arg watchdir: the absolute path to the directory to watch
        :arg expires: the number of minutes which denote an orphaned file

        """

        now = datetime.datetime.now()
        cutoff = now - datetime.timedelta(minutes=expires)

        # Cutoff as seconds since epoch
        cutoff_epoch = cutoff.timestamp()

        # Walk the directory looking for old files and delete them and keep track
        # of the directory
        for root, dirs, files in os.walk(watchdir):
            for fn in files:
                fn = os.path.join(root, fn)
                # Time in seconds since epoch
                try:
                    mtime = os.path.getmtime(fn)
                except OSError as exc:
                    self.stderr.write(
                        f"remove_orphaned_files: Error getting mtime: {fn} {exc}"
                    )
                    metrics.incr("remove_orphaned_files.delete_file_error")
                    # OSError means we're not going to be able to delete this file. It's
                    # either gone already or we don't have access.
                    continue

                if mtime < cutoff_epoch:
                    try:
                        size = os.path.getsize(fn)
                    except OSError as exc:
                        self.stderr.write(
                            f"remove_orphaned_files: Error getting size: {fn} {exc}"
                        )
                        metrics.incr("remove_orphaned_files.delete_file_error")
                        # OSError means we're not going to be able to delete this file.
                        # It's either gone already or we don't have access.
                        continue

                    try:
                        os.remove(fn)
                        self.stdout.write(
                            f"remove_orphaned_files: Deleted file: {fn}, {size}b"
                        )
                        metrics.incr("remove_orphaned_files.delete_file")
                    except OSError as exc:
                        self.stderr.write(
                            f"remove_orphaned_files: Error deleting file: {fn} {exc}"
                        )
                        metrics.incr("remove_orphaned_files.delete_file_error")

    def handle(self, *args, **options):
        is_daemon = options["daemon"]
        is_verbose = options["verbose"]

        watchdir = settings.UPLOAD_TEMPDIR
        expires = settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF

        self.stdout.write(f"remove_orphaned_files: Expires: {expires:,}m")
        self.stdout.write(f"remove_orphaned_files: Watchdir: {watchdir!r}")
        if is_daemon:
            self.stdout.write(
                "remove_orphaned_files: Daemon mode on: will check every 5 minutes."
            )
        if is_verbose:
            self.stdout.write("remove_orphaned_files: Verbose: on")

        watchdir = os.path.abspath(str(watchdir))
        if not os.path.exists(watchdir):
            self.stderr.write(
                f"remove_orphaned_files: Error: {watchdir!r} does not exist. Exiting."
            )
            return 1

        while True:
            self.delete_orphans(watchdir=watchdir, expires=expires)
            if not is_daemon:
                break

            if is_verbose:
                self.stderro.write("remove_orphaned_files: Sleeping {SLEEP_TIME}...")
            time.sleep(SLEEP_TIME)
