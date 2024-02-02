#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generate a list of sym files as a CSV for testing downloads.
#
# Usage: ./bin/setup-download-tests.py [OPTIONS] --auth-token="${PROD_AUTH_TOKEN}" [OUTPUTDIR]

import csv
import datetime
import os
import tempfile
from urllib.parse import urljoin

import click

from systemtests.utils import build_zip_file, download_sym_file, get_sym_files


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600

SYMBOLS_URL = "https://symbols.mozilla.org/"

# Download tests data file (CSV) config
SYM_FILENAMES_FOR_NEGATIVE_TESTS = [
    "libEGL.so/8787CB75CD6E976D87477CA9AC1EB98D0/libEGL.so.sym",
    "libvlc.dll/3BDB3BCF29000/libvlc.dl_",
]
REQUIRED_FILE_TYPES = ["try", "mac", "linux", "windows"]


def check_platform(sym_filename):
    sym_filename_lowercase = sym_filename.lower()

    # TODO: Are these right?
    # Reference: https://wiki.mozilla.org/Breakpad:Symbols#How_symbols_get_to_the_symbol_server
    def is_mac():
        return ".dsym" in sym_filename_lowercase

    def is_linux():
        return ".dbg" in sym_filename_lowercase or ".so" in sym_filename_lowercase

    def is_windows():
        return (
            ".pdb" in sym_filename_lowercase
            or ".exe" in sym_filename_lowercase
            or ".dll" in sym_filename_lowercase
        )

    if is_mac():
        return "mac"
    if is_linux():
        return "linux"
    if is_windows():
        return "windows"
    else:
        return None


def iterate_through_symbols_files(
    auth_token,
    sym_files_url,
    start_page,
    sym_filenames,
    sym_file_type_to_filename,
    end_condition_num_files,
):
    sym_files_generator = get_sym_files(auth_token, sym_files_url, start_page)
    for sym_filename, _ in sym_files_generator:
        if sym_filename.endswith(".0"):
            # Skip these because there aren't SYM files for them.
            continue

        is_try = False

        click.echo(
            click.style(
                f"Checking {sym_filename} to see if it should be added to the list of sym files...",
                fg="yellow",
            )
        )

        if sym_filename.startswith("try/"):
            sym_filename = sym_filename[4:]
            is_try = True

        if sym_filename.startswith("v1/"):
            sym_filename = sym_filename[3:]

        file_type = check_platform(sym_filename)
        build_list_of_sym_filenames(
            sym_filename,
            file_type,
            is_try,
            sym_filenames,
            sym_file_type_to_filename,
        )

        if len(sym_filenames) >= end_condition_num_files:
            break


def build_list_of_sym_filenames(
    sym_filename, file_type, is_try, sym_filenames, sym_file_type_to_filename
):
    """
    Builds up a sym_file_type_to_filename map of the form:

    {
        try: {filename1},
        linux: {filename2},
        mac: {filename3},
        windows: {filename4}
    }

    Where each filename occurs at most once as a value in the map, and the
    only try file is filename1.
    """
    # TODO: if file already exists and isn't expired, return
    # TODO: We might want to have a .sym file in our list as well; since they're
    # the most common file type FWICT
    # TODO: Do we need sym_filenames? Can we get rid of it in favor of using
    # the Python equivalent of Object.keys(sym_file_type_to_filename)?
    if file_type is None:
        return

    # The same file could be both a try file and a platform file,
    # so check for both (try first).
    if is_try:
        if "try" not in sym_file_type_to_filename:
            click.echo(
                click.style(
                    f"Adding {sym_filename} to the list as file type: try ...",
                    fg="green",
                )
            )
            sym_file_type_to_filename["try"] = sym_filename
            sym_filenames.append(sym_filename)
            return
        # If we ensure any of our platform file types (mac, linux, windows) are from the
        # regular bucket only, we can guarantee we get the download URL right based on
        # the correct bucket downstream.
        return

    if file_type in sym_file_type_to_filename:
        return

    click.echo(
        click.style(
            f"Adding {sym_filename} to the list as file type: {file_type} ...",
            fg="green",
        )
    )
    sym_file_type_to_filename[file_type] = sym_filename
    sym_filenames.append(sym_filename)


def write_list_of_sym_filenames_to_csv(
    sym_filenames, sym_file_type_to_filename, outputdir
):
    # TODO: if file already exists and isn't expired, return
    # TODO: Make the comments as similar to the original hardcoded CSV as possible
    # Check if we're missing any file types
    file_types = list(sym_file_type_to_filename.keys())
    file_types.sort()
    REQUIRED_FILE_TYPES.sort()
    if file_types != REQUIRED_FILE_TYPES:
        click.echo(
            click.style(
                f"Missing file types for download test ... Needed: {REQUIRED_FILE_TYPES} Have: {file_types}",
                fg="red",
            )
        )

    # TODO: Add what type of file it is to the CSV (i.e. try, mac, linux, windows, ...)
    click.echo(f"Writing SYM filenames to CSV in {outputdir} ...")
    csv_rows = []
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    csv_rows.append([f"# File built: {date}"])
    csv_rows.append(["# Format: symfile", "expected status code"])
    csv_rows.append(["# NOTE: None of these should take over 1000ms to download."])
    # These are recent uploads, so they're 200.
    for sym_filename in sym_filenames:
        csv_rows.append([sym_filename, 200])
    # These were from tecken-loadtests and have expired, so they're 404.
    for sym_filename in SYM_FILENAMES_FOR_NEGATIVE_TESTS:
        csv_rows.append([sym_filename, 404])
    with open(f"{outputdir}", "w") as f:
        write = csv.writer(f)
        write.writerows(csv_rows)


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
@click.argument("csv_output_path")
@click.argument("zip_output_dir")
@click.pass_context
def setup_download_tests(ctx, auth_token, start_page, csv_output_path, zip_output_dir):
    """
    Generates a list of sym files, writes them to a CSV, and downloads
    them to a zip folder. This is used for the download symbols tests.

    Note: This requires an auth token for symbols.mozilla.org to view files.

    """
    sym_filenames = []

    # We want at least one SYM file from the /try bucket and one from each platform,
    # so initialize a map to keep track of what file types we have
    sym_file_type_to_filename = {}

    click.echo("Fetching symbols files ...")
    # Get a try symbol first. Since these are more rare, add a key filter in the URL
    sym_files_url = urljoin(SYMBOLS_URL, "/api/uploads/files?key=try/")
    end_condition_num_files = 1
    iterate_through_symbols_files(
        auth_token,
        sym_files_url,
        start_page,
        sym_filenames,
        sym_file_type_to_filename,
        end_condition_num_files,
    )

    # Get regular symbols files
    sym_files_url = urljoin(SYMBOLS_URL, "/api/uploads/files/")
    end_condition_num_files = len(REQUIRED_FILE_TYPES)
    iterate_through_symbols_files(
        auth_token,
        sym_files_url,
        start_page,
        sym_filenames,
        sym_file_type_to_filename,
        end_condition_num_files,
    )

    if not os.path.exists(zip_output_dir):
        # Create the zip output directory if it doesn't exist
        os.makedirs(zip_output_dir)

    # Figure out the ZIP file name and final path
    zip_filename = datetime.datetime.now().strftime("symbols_%Y%m%d_%H%M%S.zip")
    zip_path = os.path.join(zip_output_dir, zip_filename)

    # Download the list of sym files to a temporary directory and then zip them
    # to the specified zip output directory
    with tempfile.TemporaryDirectory(prefix="symbols") as tmpdirname:
        sym_dir = os.path.join(tmpdirname, "syms")
        for file_type, sym_filename in sym_file_type_to_filename.items():
            url = urljoin(SYMBOLS_URL, sym_filename)
            if file_type == "try":
                url = url + "?try"
            sym_file = os.path.join(sym_dir, sym_filename)
            click.echo(
                click.style(
                    f"Downloading {sym_filename} to a temporary location before zipping ...",
                    fg="green",
                )
            )
            download_sym_file(url, sym_file)

        click.echo(
            click.style(
                f"Adding {sym_filenames} to the zip file at {zip_path} ...",
                fg="green",
            )
        )
        build_zip_file(zip_path, sym_dir)

    write_list_of_sym_filenames_to_csv(
        sym_filenames, sym_file_type_to_filename, csv_output_path
    )

    click.echo(f"Created {csv_output_path} with list of SYM files for download tests.")


if __name__ == "__main__":
    setup_download_tests()
