#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Download a sym file and save it to disk.

# Usage: download-sym.py [outputdir] [debugid] [debugfilename]

import os
from urllib.parse import urljoin

import click
import requests


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for downloading SYM files.",
)
@click.argument("outputdir")
@click.argument("debugid")
@click.argument("debugfilename")
@click.pass_context
def download_sym_file(ctx, base_url, outputdir, debugid, debugfilename):
    """Downloads a sym file given a debug id and debug filename."""
    # Download sym file
    path = f"{debugfilename}/{debugid}/{debugfilename}.sym"
    url = urljoin(base_url, path)
    headers = {"User-Agent": "tecken-download-sym"}

    click.echo(f"Downloading {url} ...")
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        click.echo(
            click.style(f"ERROR: status code: {url} HTTP {resp.status_code}", fg="red")
        )
        ctx.exit(1)

    # Write file to disk
    dest = os.path.join(outputdir, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    with open(dest, "wb") as fp:
        fp.write(resp.content)

    click.echo(f"Wrote {len(resp.content):,} bytes to {dest}.")


if __name__ == "__main__":
    download_sym_file()
