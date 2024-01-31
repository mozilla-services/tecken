#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generate a list of sym files as a CSV for testing downloads.
#
# Usage: ./bin/setup-download-tests.py [OPTIONS] --auth-token="${PROD_AUTH_TOKEN}" [OUTPUTDIR]

import datetime
import os
import shutil
import tempfile
from urllib.parse import urljoin
import zipfile

import click
import requests

import csv


# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600

SYMBOLS_URL = "https://symbols.mozilla.org/"

# Download tests data file (CSV) config
SYM_FILENAMES_FOR_NEGATIVE_TESTS = [
    "libEGL.so/8787CB75CD6E976D87477CA9AC1EB98D0/libEGL.so.sym",
    "libvlc.dll/3BDB3BCF29000/libvlc.dl_",
]
REQUIRED_FILE_TYPES = ["try", "mac", "linux", "windows"]


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
):  # TODO: if file already exists and isn't expired, return
    # TODO: We might want to have a .sym file in our list as well; since they're
    # the most common file type FWICT
    if file_type is None:
        return

    # The same file could be both a try file and a platform file,
    # so check for both (try first).
    if is_try and "try" not in sym_file_type_to_filename:
        click.echo(
            click.style(
                f"Adding {sym_filename} to the list as file type: try ...", fg="green"
            )
        )
        sym_file_type_to_filename["try"] = sym_filename
        sym_filenames.append(sym_filename)

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
@click.argument("outputdir")
@click.pass_context
def setup_download_tests(ctx, auth_token, start_page, outputdir):
    """
    Writes a subset of the SYM files' filenames to a CSV.
    This is used for the download symbols tests.

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

    write_list_of_sym_filenames_to_csv(
        sym_filenames, sym_file_type_to_filename, outputdir
    )

    click.echo(f"Created {outputdir} with list of SYM files for download tests.")


if __name__ == "__main__":
    setup_download_tests()
