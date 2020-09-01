#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Download SYM files and put them into a ZIP file for testing upload with.
#
# Usage: ./bin/make-zymbols-zip.py [OUTPUTDIR]

import datetime
import os
import shutil
import tempfile
from urllib.parse import urljoin
import zipfile

import click
import requests


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 60

SYMBOLS_URL = "https://symbols.mozilla.org/"


def get_sym_files(auth_token, url, start_page):
    """Given an auth token, generates filenames and sizes for SYM files.

    :param auth_token: auth token for symbols.mozilla.org
    :param url: url for file uploads
    :param start_page: the page of files to start with

    :returns: generator of (key, size) typles

    """
    sym_files = []
    page = start_page
    params = {"page": start_page}
    headers = {"auth-token": auth_token, "User-Agent": "tecken-systemtests"}

    while True:
        if sym_files:
            yield sym_files.pop(0)
        else:
            params["page"] = page
            resp = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=CONNECTION_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            sym_files = [(record["key"], record["size"]) for record in data["files"]]
            page += 1


def build_zip_file(zip_filename, sym_dir):
    """Generates a ZIP file of contents of sym dir.

    :param zip_filename: full path to zip file
    :param sym_dir: full path to directory of SYM files

    :returns: path to zip file

    """
    # Create zip file
    with zipfile.ZipFile(zip_filename, mode="w") as fp:
        for root, dirs, files in os.walk(sym_dir):
            if not files:
                continue

            for sym_file in files:
                full_path = os.path.join(root, sym_file)
                arcname = full_path[len(sym_dir) + 1 :]

                fp.write(
                    full_path,
                    arcname=arcname,
                    compress_type=zipfile.ZIP_DEFLATED,
                )


def download_sym_file(url, sym_file):
    """Download SYM file into sym_dir."""
    headers = {"User-Agent": "tecken-systemtests"}
    resp = requests.get(url, headers=headers, timeout=CONNECTION_TIMEOUT)
    if resp.status_code != 200:
        return

    dirname = os.path.dirname(sym_file)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(sym_file, "wb") as fp:
        fp.write(resp.content)


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
@click.pass_context
def make_symbols_zip(ctx, auth_token, start_page, max_size, outputdir):
    """
    Builds a zip file of SYM files recently uploaded to symbols.mozilla.org.

    Note: This requires an auth token for symbols.mozilla.org to view files.

    """
    # Figure out the ZIP file name and final path
    zip_filename = datetime.datetime.now().strftime("symbols_%Y%m%d_%H%M%S.zip")
    zip_path = os.path.join(outputdir, zip_filename)

    click.echo("Generating ZIP file %s ..." % zip_path)
    with tempfile.TemporaryDirectory(prefix="symbols") as tmpdirname:
        sym_dir = os.path.join(tmpdirname, "syms")
        tmp_zip_path = os.path.join(tmpdirname, zip_filename)

        sym_files_url = urljoin(SYMBOLS_URL, "/api/uploads/files/")
        sym_files_generator = get_sym_files(auth_token, sym_files_url, start_page)
        for sym_filename, sym_size in sym_files_generator:
            if sym_filename.endswith(".0"):
                # Skip these because there aren't SYM files for them.
                continue

            is_try = False

            if os.path.exists(tmp_zip_path):
                # See if the new zip file is too big; if it is, we're done!
                zip_size = os.stat(tmp_zip_path).st_size
                click.echo("size: %s, max_size: %s" % (zip_size, max_size))
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
                    "Adding %s (%s) ..." % (sym_filename, sym_size), fg="yellow"
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
    click.echo("Completed %s (%s)!" % (zip_path, zip_size))


if __name__ == "__main__":
    make_symbols_zip()
