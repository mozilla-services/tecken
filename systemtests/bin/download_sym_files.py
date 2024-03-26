#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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
        click.echo(f"metric: {record.stat_type} {record.key} {record.value/1000:,.2f}s")


markus.configure([{"class": StdoutMetrics}], raise_errors=True)
METRICS = markus.get_metrics()


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for downloading SYM files.",
)
@click.argument(
    "csv_file",
    nargs=1,
    type=click.Path(),
)
def download_sym_files(base_url, csv_file):
    """Tests downloading SYM files.

    Takes a CSV file and a base url, composes urls for SYM files to download,
    and downloads them. It keeps track of timing measurements and status codes.

    The CSV file is of the form:

    SYM FILE,EXPECTED STATUS CODE
    """

    with open(csv_file) as fp:
        lines = fp.readlines()

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#"):
            # Skip commented out and blank lines
            continue

        with METRICS.timer("download_time"):
            parts = line.split(",")

            sym_filename, expected_status_code, bucket = parts

            # Compute url
            url = urljoin(base_url, sym_filename)
            if bucket == "try":
                url = url + "?try"
            click.echo(click.style(f"Working on {url} ...", fg="yellow"))

            # Download the file
            headers = {"User-Agent": "tecken-systemtests"}
            resp = requests.get(url, headers=headers, timeout=60)

            for item in resp.history:
                if item.status_code in (301, 302):
                    click.echo(f">>> redirect: {item.url}")
            click.echo(f">>> final: {resp.url}")
            click.echo(f">>> status code: {resp.status_code}")
            if resp.status_code == 200:
                click.echo(f">>> file size {len(resp.content):,} bytes")

            # Compare status code with expected status code
            if resp.status_code != int(expected_status_code):
                click.echo(
                    click.style(
                        f"FAIL: Status code: {resp.status_code} != {expected_status_code}",
                        fg="red",
                    )
                )
            else:
                click.echo(click.style("Success!", fg="green"))


if __name__ == "__main__":
    download_sym_files()
