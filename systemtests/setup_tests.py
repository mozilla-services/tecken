#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import click

from systemtests.bin.setup_download_tests import setup_download_tests
from systemtests.bin.setup_upload_tests import setup_upload_tests

# Usage: ./setup-tests.py
# This setup is only for non-prod envs (local and stage), as it uploads
# zip files to Tecken (destructive).

ZIPS_DIR = "./data/zip-files/"
PROD_AUTH_TOKEN = os.environ["PROD_AUTH_TOKEN"]


@click.command()
@click.pass_context
def setup_tests(ctx):
    if not os.path.exists(ZIPS_DIR):
        # Create the zip output directory if it doesn't exist
        os.makedirs(ZIPS_DIR)

    click.echo("Generating systemtest data files ...")
    zips_count = len(
        [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}/{name}")
        ]
    )
    if zips_count < 4:
        # Generate some symbols ZIP files to upload, and a CSV
        # of those symbols files to download
        ctx.invoke(
            setup_download_tests,
            start_page=1,
            auth_token=f"{PROD_AUTH_TOKEN}",
            csv_output_path="./data/sym_files_to_download.csv",
            zip_output_dir=f"{ZIPS_DIR}",
        )

        # Generate some symbols ZIP files to upload
        ctx.invoke(
            setup_upload_tests,
            max_size=10_000_000,
            start_page=1,
            auth_token=f"{PROD_AUTH_TOKEN}",
            outputdir=f"{ZIPS_DIR}",
        )
        ctx.invoke(
            setup_upload_tests,
            max_size=50_000_000,
            start_page=10,
            auth_token=f"{PROD_AUTH_TOKEN}",
            outputdir=f"{ZIPS_DIR}",
        )
    else:
        click.echo(f"Already have {zips_count} zip files.")


if __name__ == "__main__":
    setup_tests()
