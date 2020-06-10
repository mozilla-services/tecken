#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Download missingsymbols.csv file and prints line count.

# Usage: ./bin/download-missing-symbols.py

from urllib.parse import urljoin

import click
import requests


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for uploading SYM files.",
)
@click.pass_context
def download_missing_symbols(ctx, base_url):
    csv_url = urljoin(base_url, "/missingsymbols.csv")
    click.echo("Using: %s" % csv_url)
    resp = requests.get(csv_url)
    if resp.status_code != 200:
        click.echo(
            click.style("Error: %s %s" % (resp.status_code, resp.content), fg="red")
        )

    else:
        lines = [line.strip() for line in resp.content.splitlines()]
        click.echo(click.style("Success: Number of lines: %d" % len(lines), fg="green"))


if __name__ == "__main__":
    download_missing_symbols()
