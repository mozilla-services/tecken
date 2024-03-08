#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generate a list of sym files as a CSV for testing downloads,
# downloading and zipping them as two zip files (one for the try bucket
# and one for the regular bucket) to a local directory.
#
# Usage: ./bin/setup_download_tests.py [OPTIONS] --auth-token=[AUTH_TOKEN] [CSV_OUTPUT_PATH] [ZIP_OUTPUT_DIR]

import csv
import datetime
import os
import tempfile
from urllib.parse import urljoin

import click

from systemtestslib.utils import build_zip_file, download_sym_file, get_sym_files


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600

SYMBOLS_URL = "https://symbols.mozilla.org/"

# Download tests data file (CSV) config
SYM_FILENAMES_FOR_NEGATIVE_TESTS = [
    "libEGL.so/8787CB75CD6E976D87477CA9AC1EB98D0/libEGL.so.sym",
    "libvlc.dll/3BDB3BCF29000/libvlc.dl_",
]

REQUIRED_FILE_TYPES = ["try", "regular"]


def iterate_through_symbols_files(
    auth_token,
    sym_files_url,
    start_page,
    sym_file_type_to_filename,
    end_condition_num_files,
):
    sym_files_generator = get_sym_files(auth_token, sym_files_url, start_page)
    for sym_filename, _ in sym_files_generator:
        if sym_filename.endswith(".0"):
            # Skip these because there aren't SYM files for them.
            continue

        if not sym_filename.endswith(".sym"):
            # We only test for sym files currently
            continue

        is_try = False

        if sym_filename.startswith("try/"):
            sym_filename = sym_filename[4:]
            is_try = True

        if sym_filename.startswith("v1/"):
            sym_filename = sym_filename[3:]

        build_list_of_sym_filenames(
            sym_filename,
            is_try,
            sym_file_type_to_filename,
        )

        if len(list(sym_file_type_to_filename.values())) >= end_condition_num_files:
            break


def build_list_of_sym_filenames(sym_filename, is_try, sym_file_type_to_filename):
    """
    Builds up a sym_file_type_to_filename map of the form:

    {
        try: {filename1},
        regular: {filename2}
    }

    Where each filename occurs at most once as a value in the map.
    """
    # The same file could be both a try file and a platform file,
    # so check for both (try first).
    if is_try:
        if "try" not in sym_file_type_to_filename:
            click.echo(
                f"Adding {sym_filename} to the list as bucket: try ...",
            )
            sym_file_type_to_filename["try"] = sym_filename
            return
        # If we ensure any of our platform file types (mac, linux, windows) are from the
        # regular bucket only, we can guarantee we get the download URL right based on
        # the correct bucket downstream.
        return

    if "regular" in sym_file_type_to_filename:
        return

    click.echo(f"Adding {sym_filename} to the list as bucket: regular ...")
    sym_file_type_to_filename["regular"] = sym_filename


def write_list_of_sym_filenames_to_csv(sym_file_type_to_filename, outputdir):
    file_types = list(sym_file_type_to_filename.keys())
    file_types.sort()
    REQUIRED_FILE_TYPES.sort()
    if file_types != REQUIRED_FILE_TYPES:
        raise ValueError(
            f"Missing file types for download test ... Needed: {REQUIRED_FILE_TYPES} Have: {file_types}."
        )

    click.echo(f"Writing SYM filenames to CSV in {outputdir} ...")
    csv_rows = []
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    csv_rows.append([f"# File built: {date}"])
    csv_rows.append(["# Format: symfile", "expected status code", "bucket"])
    csv_rows.append(["# These are recent uploads, so they should return HTTP 200s."])
    for file_type, sym_filename in sym_file_type_to_filename.items():
        bucket = "regular"
        if file_type == "try":
            bucket = file_type
        csv_rows.append([sym_filename, 200, bucket])
    csv_rows.append(
        ["# These were from tecken-loadtests and have expired, so they're 404."]
    )
    for sym_filename in SYM_FILENAMES_FOR_NEGATIVE_TESTS:
        csv_rows.append([sym_filename, 404, bucket])

    with open(f"{outputdir}", "w", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\n")
        for row in csv_rows:
            if row[0].startswith(("#", "@")):
                fp.write(f"{row[0]}\n")
            else:
                writer.writerow(row)


def download_and_zip_files(zip_path, subset_to_zip):
    with tempfile.TemporaryDirectory(prefix="symbols") as tmpdirname:
        sym_dir = os.path.join(tmpdirname, "syms")
        for (
            file_type,
            sym_filename,
        ) in subset_to_zip.items():
            url = urljoin(SYMBOLS_URL, sym_filename)
            if file_type == "try":
                url = url + "?try"
            sym_file = os.path.join(sym_dir, sym_filename)
            click.echo(
                f"Downloading {sym_filename} to a temporary location before zipping ...",
            )
            download_sym_file(url, sym_file)

        click.echo(
            f"Zipping {list(subset_to_zip.values())} to {zip_path} ...",
        )
        build_zip_file(zip_path, sym_dir)


def get_subset_to_zip(is_try, sym_file_type_to_filename):
    """
    From the overall set of sym files in the provided map, return a
    subset of just the try files or just the regular files.
    """
    subset_to_zip = dict.copy(sym_file_type_to_filename)
    if is_try:
        # delete all but the try key-value pairs
        keys_to_delete = [elem for elem in sym_file_type_to_filename if elem != "try"]
        for key in keys_to_delete:
            del subset_to_zip[key]
    else:
        # delete the try key-value pairs
        del subset_to_zip["try"]
    return subset_to_zip


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
def setup_download_tests(start_page, auth_token, csv_output_path, zip_output_dir):
    """
    Generates a list of sym files, writes them to a CSV, and downloads
    them to two separate zip folders: one for try symbols files, and one for
    regular symbols files. This is used for the download system tests.

    Note: This requires an auth token for symbols.mozilla.org to view files.

    """
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
        sym_file_type_to_filename,
        end_condition_num_files,
    )

    # Figure out the ZIP file names and final path
    # Try files go into a separate zip from regular files, so they
    # can be uploaded to the correct bucket later as part of the
    # upload system tests.
    zip_filename_try = datetime.datetime.now().strftime(
        "symbols_%Y%m%d_%H%M%S__try.zip"
    )
    zip_filename_regular = datetime.datetime.now().strftime(
        "symbols_%Y%m%d_%H%M%S__regular.zip"
    )
    zip_path_try = os.path.join(zip_output_dir, zip_filename_try)
    zip_path_regular = os.path.join(zip_output_dir, zip_filename_regular)

    # Download the list of sym files to a temporary directory and then zip them
    # to the specified zip output directory.
    subset_to_zip_try = get_subset_to_zip(True, sym_file_type_to_filename)
    subset_to_zip_regular = get_subset_to_zip(False, sym_file_type_to_filename)
    download_and_zip_files(zip_path_try, subset_to_zip_try)
    click.echo(
        click.style(
            f"Zipped {subset_to_zip_try} to {zip_path_try} ...",
            fg="yellow",
        )
    )
    download_and_zip_files(zip_path_regular, subset_to_zip_regular)
    click.echo(
        click.style(
            f"Zipped {subset_to_zip_regular} to {zip_path_regular} ...",
            fg="yellow",
        )
    )

    write_list_of_sym_filenames_to_csv(sym_file_type_to_filename, csv_output_path)
    click.echo(
        click.style(
            f"Created {csv_output_path} with list of SYM files for download tests.",
            fg="yellow",
        )
    )


if __name__ == "__main__":
    setup_download_tests()
