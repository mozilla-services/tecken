# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Utilities used to setup upload and download system tests.

import os
import zipfile

import requests
import tenacity


# Default HTTP timeout to use when not specified--this is both the connection and read
# timeout
HTTP_TIMEOUT = 10

# Number of seconds to wait for a response from server when downloading potentially
# large files
HTTP_DOWNLOAD_TIMEOUT = 600


def _is_retryable_status_code(resp):
    return resp.status_code in (429, 500, 503)


@tenacity.retry(
    retry=(
        tenacity.retry_if_exception_type(requests.RequestException)
        | tenacity.retry_if_result(_is_retryable_status_code)
    ),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
    stop=tenacity.stop_after_attempt(5),
    reraise=True,
)
def http_get_with_retry(*args, **kwargs):
    """Performs a retryable requests.get

    This retries on any request exception (e.g. timeout) as well as any 429, 500, or
    503 status code.

    This adds a default timeout of HTTP_TIMEOUT seconds if none is specified.

    Arguments are request.get arguments.

    :raises requests.exceptions.RequestException: if it run out of retry attempts
        because an exception is thrown, the exceptions is re-raised
    :raises tenacity.RetryError: if it runs out of retry attempts because of status code

    :returns: requests.Response if successful

    """
    if "timeout" not in kwargs:
        kwargs["timeout"] = HTTP_TIMEOUT
    return requests.get(*args, **kwargs)


@tenacity.retry(
    retry=(
        tenacity.retry_if_exception_type(requests.RequestException)
        | tenacity.retry_if_result(_is_retryable_status_code)
    ),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
    stop=tenacity.stop_after_attempt(5),
    reraise=True,
)
def http_head_with_retry(*args, **kwargs):
    """Performs a retryable requests.head

    This retries on any request exception (e.g. timeout) as well as any 429, 500, or
    503 status code.

    This adds a default timeout of HTTP_TIMEOUT seconds if none is specified.

    Arguments are request.head arguments.

    :raises requests.exceptions.RequestException: if it run out of retry attempts
        because an exception is thrown, the exceptions is re-raised
    :raises tenacity.RetryError: if it runs out of retry attempts because of status code

    :returns: requests.Response if successful

    """
    if "timeout" not in kwargs:
        kwargs["timeout"] = HTTP_TIMEOUT
    return requests.head(*args, **kwargs)


def http_post(*args, **kwargs):
    """Performs a requests.post

    This adds a default timeout of HTTP_TIMEOUT seconds if none is specified.

    Arguments are request.post arguments.

    :raises requests.exceptions.RequestException: if it run out of retry attempts
        because an exception is thrown, the exceptions is re-raised

    :returns: requests.Response if successful

    """
    if "timeout" not in kwargs:
        kwargs["timeout"] = HTTP_TIMEOUT
    return requests.post(*args, **kwargs)


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
            resp = http_get_with_retry(
                url,
                params=params,
                headers=headers,
                timeout=HTTP_DOWNLOAD_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            sym_files = [
                (record["key"], record["size"])
                for record in data["files"]
                if record["completed_at"]
            ]
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
    resp = http_get_with_retry(url, headers=headers, timeout=HTTP_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()

    dirname = os.path.dirname(sym_file_path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(sym_file_path, "wb") as fp:
        fp.write(resp.content)
