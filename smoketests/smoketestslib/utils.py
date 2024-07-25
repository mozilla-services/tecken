# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Utilities used to setup upload and download smoke tests.

import os
from urllib.parse import urljoin
import zipfile

import requests

# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 600


def get_sym_files(baseurl, auth_token, params):
    """Given an auth token, generates filenames and sizes for SYM files.

    :param baseurl: a base url
    :param auth_token: an auth token
    :param params: a dict of parameters to pass by querystring.

    :returns: generator of (key, size) typles

    """
    url = urljoin(baseurl.rstrip("/"), "/api/uploads/files")
    headers = {"auth-token": auth_token, "User-Agent": "tecken-smoketests"}
    params = params or {}

    sym_files = []
    page = params.get("page", 1)

    while True:
        params["page"] = page
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=CONNECTION_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        sym_files = [
            (record["key"], record["size"])
            for record in data["files"]
            if record["completed_at"]
        ]
        yield from sym_files

        # NOTE(willkg): sometimes a whole bunch of try uploads happen at the same
        # time and since there's no way to filter for just regular symbols files (as
        # opposed to try symbols files), this code ends up spending 30s per GET
        # request for 10-20 pages which takes a long time.
        #
        # Instead of doing that, we do this thing where we change the increment
        # to move through pages faster in hopes it results in fewer GET requests.
        if page < 3:
            page += 1
        else:
            page += 5


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
    headers = {"User-Agent": "tecken-smoketests"}
    resp = requests.get(url, headers=headers, timeout=CONNECTION_TIMEOUT)
    resp.raise_for_status()

    dirname = os.path.dirname(sym_file_path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(sym_file_path, "wb") as fp:
        fp.write(resp.content)
