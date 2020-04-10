#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Download symbols files.
#
# Usage: ./bin/download-sym-files.py CSVFILE

from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase
import requests


class StdoutMetrics(BackendBase):
    def emit(self, record):
        click.echo(
            "Elapsed time: %s %s %s" % (record.stat_type, record.key, record.value)
        )


markus.configure([{"class": StdoutMetrics}], raise_errors=True)
METRICS = markus.get_metrics()


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for downloading SYM files.",
)
@click.argument(
    "csv_file", nargs=1, type=click.Path(),
)
def download_sym_files(base_url, csv_file):
    """Tests downloading SYM files.

    Takes a CSV file and a base url, composes urls for SYM files to download,
    and downloads them. It keeps track of timing measurements and status codes.

    The CSV file is of the form:

    SYM FILE,EXPECTED STATUS CODE
    """

    with open(csv_file, "r") as fp:
        lines = fp.readlines()

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#"):
            # Skip commented out and blank lines
            continue

        if line.startswith("@ECHO"):
            # This lets us encode directions for the viewer in the csv files
            click.echo(click.style(line[5:].strip(), fg="yellow"))
            continue

        with METRICS.timer("download_time"):
            parts = line.split(",")

            # Compute url
            url = urljoin(base_url, parts[0])
            click.echo(click.style("Working on %s ..." % url, fg="yellow"))

            # Download the file
            resp = requests.get(url)

            # Compare status code with expected status code
            if resp.status_code != int(parts[1]):
                click.echo(
                    click.style(
                        "FAIL: Status code: %s != %s" % (resp.status_code, parts[1]),
                        fg="red",
                    )
                )


if __name__ == "__main__":
    download_sym_files()
