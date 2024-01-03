# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from tecken.libmarkus import METRICS


logger = logging.getLogger("tecken.remove_orphaned_files")


class Command(BaseCommand):
    help = "Watch upload_tempdir directory for orphaned files and delete them."

    def add_arguments(self, parser):
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
        for root, _, files in os.walk(watchdir):
            for fn in files:
                fn = os.path.join(root, fn)
                # Time in seconds since epoch
                try:
                    mtime = os.path.getmtime(fn)
                except FileNotFoundError:
                    # if there's nothing to delete then we are done here
                    continue
                except OSError:
                    logger.exception("error getting mtime: %s", fn)
                    METRICS.incr("remove_orphaned_files.delete_file_error")
                    # OSError means we're not going to be able to delete this file. It's
                    # either gone already or we don't have access.
                    continue

                if mtime < cutoff_epoch:
                    try:
                        size = os.path.getsize(fn)
                    except FileNotFoundError:
                        # if there's nothing to delete then we are done here
                        continue
                    except OSError:
                        logger.exception("error getting size: %s", fn)
                        METRICS.incr("remove_orphaned_files.delete_file_error")
                        # OSError means we're not going to be able to delete this file.
                        # It's either gone already or we don't have access.
                        continue

                    try:
                        os.remove(fn)
                        logger.info("deleted file: %s, %sb", fn, size)
                        METRICS.incr("remove_orphaned_files.delete_file")
                    except FileNotFoundError:
                        # if there's nothing to delete then we are done here
                        continue
                    except OSError:
                        logger.exception("error deleting file: %s", fn)
                        METRICS.incr("remove_orphaned_files.delete_file_error")

    def handle(self, *args, **options):
        is_verbose = options["verbose"]

        watchdir = settings.UPLOAD_TEMPDIR
        expires = settings.UPLOAD_TEMPDIR_ORPHANS_CUTOFF

        logger.info("expires: %s (minutes)", expires)
        logger.info("watchdir: %r", watchdir)
        if is_verbose:
            logger.info("verbose: on")

        watchdir = os.path.abspath(str(watchdir))
        if not os.path.exists(watchdir):
            logger.info("%r does not exist", watchdir)
            return 0

        self.delete_orphans(watchdir=watchdir, expires=expires)
