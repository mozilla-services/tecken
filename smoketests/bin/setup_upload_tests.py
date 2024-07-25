#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Download SYM files and put them into a ZIP file for testing upload with.
#
# Usage: ./bin/make-zymbols-zip.py [OUTPUTDIR]

import datetime
import os
import shutil
import tempfile
from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase

from smoketestslib.utils import build_zip_file, download_sym_file, get_sym_files


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600

SYMBOLS_URL = "https://symbols.mozilla.org/"


class StdoutMetrics(BackendBase):
    def emit(self, record):
        click.echo(f"metric: {record.stat_type} {record.key} {record.value/1000:,.2f}s")


markus.configure([{"class": StdoutMetrics}], raise_errors=True)
METRICS = markus.get_metrics()


def get_size(filename):
    """Get the size of a file.

    :param filename: the filename to check

    :returns: 0 if the file doesn't exist; file size otherwise

    """
    if not os.path.exists(filename):
        return 0

    return os.stat(filename).st_size


@click.command()
@click.option(
    "--auth-token",
    required=True,
    help="Auth token for symbols.mozilla.org.",
)
@click.option(
    "--start-page",
    default=1,
    type=int,
    help="Page of SYM files to start with.",
)
@click.option(
    "--max-size",
    default=10_000_000,
    type=int,
    help="Max size in bytes resulting ZIP file can't exceed.",
)
@click.argument("outputdir")
def setup_upload_tests(max_size, start_page, auth_token, outputdir):
    """
    Builds a zip file of SYM files recently uploaded to symbols.mozilla.org.

    Note: This requires an auth token for symbols.mozilla.org to view files.

    """
    # Figure out the ZIP file name and final path
    zip_filename = datetime.datetime.now().strftime(
        "symbols_%Y%m%d_%H%M%S__regular.zip"
    )
    zip_path = os.path.join(outputdir, zip_filename)

    with METRICS.timer("elapsed_time"):
        click.echo(f"Generating ZIP file {zip_path} ...")
        with tempfile.TemporaryDirectory(prefix="symbols") as tmpdirname:
            sym_dir = os.path.join(tmpdirname, "syms")
            tmp_zip_path = os.path.join(tmpdirname, zip_filename)

            params = {
                "page": start_page,
                "size": "< 10mb",
            }

            sym_files_generator = get_sym_files(
                baseurl=SYMBOLS_URL,
                auth_token=auth_token,
                params=params,
            )
            for sym_filename, sym_size in sym_files_generator:
                if sym_filename.endswith(".0"):
                    # Skip these because there aren't SYM files for them.
                    continue

                is_try = False

                if os.path.exists(tmp_zip_path):
                    # See if the new zip file is too big; if it is, we're done!
                    zip_size = os.stat(tmp_zip_path).st_size
                    click.echo(f"size: {zip_size:,}, max_size: {max_size:,}")
                    if zip_size > max_size:
                        # Handle weird case where the first zip file we built was
                        # too big--just use that.
                        if not os.path.exists(zip_path):
                            shutil.copy(tmp_zip_path, zip_path)
                        break

                    # This zip file isn't too big, so copy it over.
                    shutil.copy(tmp_zip_path, zip_path)

                click.echo(
                    click.style(
                        f"Adding {sym_filename} ({sym_size:,}) ...", fg="yellow"
                    )
                )

                # Download SYM file into temporary directory
                if sym_filename.startswith("try/"):
                    sym_filename = sym_filename[4:]
                    is_try = True

                if sym_filename.startswith("v1/"):
                    sym_filename = sym_filename[3:]

                url = urljoin(SYMBOLS_URL, sym_filename)
                if is_try:
                    url = url + "?try"
                sym_file = os.path.join(sym_dir, sym_filename)
                download_sym_file(url, sym_file)

                # Build the new zip file
                build_zip_file(tmp_zip_path, sym_dir)

        zip_size = os.stat(zip_path).st_size
        click.echo(f"Completed {zip_path} ({zip_size:,})!")


if __name__ == "__main__":
    setup_upload_tests()
