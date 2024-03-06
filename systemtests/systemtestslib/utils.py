# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Utilities used to setup upload and download system tests.

import os
import zipfile

import requests

# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600


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
        for root, _, files in os.walk(sym_dir):
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


def download_sym_file(url, sym_file_path):
    """Download SYM file at url into sym_file_path."""
    headers = {"User-Agent": "tecken-systemtests"}
    resp = requests.get(url, headers=headers, timeout=CONNECTION_TIMEOUT)
    if resp.status_code != 200:
        # FIXME: Retry request and Response.raise_for_status
        return

    dirname = os.path.dirname(sym_file_path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(sym_file_path, "wb") as fp:
        fp.write(resp.content)
