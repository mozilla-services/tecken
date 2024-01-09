#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Upload a single sym file.
#
# Usage: ./bin/upload-sym.py [SYMFILE]

import datetime
import json
import os
import tempfile
from urllib.parse import urljoin
import zipfile

import click
import requests


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600


@click.command()
@click.option(
    "--auth-token",
    required=True,
    help="Auth token for symbols.mozilla.org.",
)
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for downloading SYM files.",
)
@click.argument("symfile")
@click.pass_context
def upload_sym_file(ctx, auth_token, base_url, symfile):
    """Uploads a sym file."""
    with open(symfile, "r") as fp:
        lines = fp.readlines()

    firstline = lines[0]
    if not firstline.startswith("MODULE"):
        click.echo(click.style(f"{symfile} doesn't appear to be a sym file.", fg="red"))
        ctx.exit(1)

    parts = firstline.split(" ")
    debugid = parts[3].strip()
    debugfilename = parts[4].strip()
    if debugfilename.endswith(".pdb"):
        sym_file = debugfilename[:-4] + ".sym"
    else:
        sym_file = debugfilename + ".sym"

    path = f"{debugfilename}/{debugid}/{sym_file}"
    with tempfile.TemporaryDirectory(prefix="symbols") as tmpdirname:
        zip_filename = datetime.datetime.now().strftime("symbols_%Y%m%d_%H%M%S.zip")
        zip_path = os.path.join(tmpdirname, zip_filename)

        click.echo(f"Generating zip file {zip_path} ...")
        click.echo(f"Adding {symfile} {path} ...")
        with zipfile.ZipFile(zip_path, mode="w") as fp:
            fp.write(
                symfile,
                arcname=path,
                compress_type=zipfile.ZIP_DEFLATED,
            )

        url = urljoin(base_url, "/upload/")
        headers = {"auth-token": auth_token, "User-Agent": "tecken-upload-sym"}
        basename = os.path.basename(zip_path)

        click.echo(f"Uploading to {url} ...")

        with open(zip_path, "rb") as fp:
            resp = requests.post(
                url,
                files={basename: fp},
                headers=headers,
                timeout=CONNECTION_TIMEOUT,
            )
            if resp.status_code != 201:
                click.echo(f"ERROR: status code {resp.status_code}")
                click.echo(f"{resp.content}")
                ctx.exit(1)

            click.echo(json.dumps(json.loads(resp.content), indent=2, sort_keys=True))


if __name__ == "__main__":
    upload_sym_file()
