#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Download symbols files.
#
# Usage: ./bin/download-sym-files.py CSVFILE

from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase
import requests
from unittest.mock import ANY

# These are exclusively security headers added by nginx
TECKEN_RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ANY,
    "Strict-Transport-Security": "max-age=31536000",
}

STORAGE_BACKEND_RESPONSE_HEADERS = {
    "Content-Encoding": "gzip",
    "Content-Length": ANY,
}


class StdoutMetrics(BackendBase):
    def emit(self, record):
        click.echo(f"metric: {record.stat_type} {record.key} {record.value/1000:,.2f}s")


markus.configure([{"class": StdoutMetrics}], raise_errors=True)
METRICS = markus.get_metrics()


# Check the response headers for both the Tecken redirect response and the storage
# backend response.
def check_headers(response):
    for item in response.history:
        if item.status_code in (301, 302):
            click.echo(f">>> GET redirect: {item.url}")
            for expected_key, expected_value in TECKEN_RESPONSE_HEADERS.items():
                if expected_key not in item.headers:
                    click.echo(
                        click.style(
                            f">>> FAIL: GET expected redirect response header {expected_key} is missing.",
                            fg="red",
                        )
                    )
                    continue

                if item.headers[expected_key] == expected_value:
                    click.echo(
                        click.style(
                            f">>> SUCCESS: GET expected redirect response header {expected_key}: {expected_value}.",
                            fg="green",
                        )
                    )
                else:
                    click.echo(
                        click.style(
                            f"""
>>> FAIL: GET expected response header {expected_key} does not have expected value:
actual: {item.headers[expected_key]}
expected: {expected_value}
""",
                            fg="red",
                        )
                    )

    for (
        expected_key,
        expected_value,
    ) in STORAGE_BACKEND_RESPONSE_HEADERS.items():
        if expected_key not in response.headers:
            click.echo(
                click.style(
                    f">>> FAIL: GET expected response header {expected_key} is missing.",
                    fg="red",
                )
            )
            continue

        if response.headers[expected_key] == expected_value:
            click.echo(
                click.style(
                    f">>> SUCCESS: GET expected response header {expected_key}: {expected_value}.",
                    fg="green",
                )
            )
        else:
            click.echo(
                click.style(
                    f"""
>>> FAIL: GET expected response header {expected_key} does not have expected value:
actual: {response.headers[expected_key]}
expected: {expected_value}
""",
                    fg="red",
                )
            )


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for downloading SYM files.",
)
@click.option(
    "--test-headers",
    type=bool,
    default=True,
    help="Whether to check response headers from the Tecken redirect response and the storage backend response. Should be False for local and True otherwise.",
)
@click.argument(
    "csv_file",
    nargs=1,
    type=click.Path(),
)
def download_sym_files(base_url, test_headers, csv_file):
    """Tests downloading SYM files.

    Takes a CSV file and a base url, composes urls for SYM files to download,
    and downloads them. It keeps track of timing measurements and status codes.

    The CSV file is of the form:

    SYM FILE,EXPECTED STATUS CODE
    """

    with open(csv_file) as fp:
        lines = fp.readlines()

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#"):
            # Skip commented out and blank lines
            continue

        with METRICS.timer("download_time"):
            parts = line.split(",")

            sym_filename, expected_status_code, bucket = parts

            # Compute url
            url = urljoin(base_url, sym_filename)
            if bucket == "try":
                url = url + "?try"
            click.echo(click.style(f"Working on {url} ...", fg="yellow"))

            headers = {
                "User-Agent": "tecken-smoketests",
                # We know storage backends will honor "Accept-Encoding": "gzip",
                # so we test the unusual case only to ensure the response is
                # still gzipped.
                "Accept-Encoding": "identity",
            }

            for method in ["HEAD", "GET"]:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=60,
                )

                if resp.status_code != int(expected_status_code):
                    click.echo(
                        click.style(
                            f"FAIL: {method} status code: {resp.status_code} != {expected_status_code}",
                            fg="red",
                        )
                    )
                else:
                    click.echo(click.style(f"SUCCESS: {method} request!", fg="green"))

                # We're interested in the success case for a request when testing headers.
                # Non-200 responses won't necessarily have the same response headers;
                # e.g. Content-Encoding isn't included in a 404 response.
                if method == "GET" and expected_status_code == "200" and test_headers:
                    check_headers(resp)

            click.echo(f">>> {method} final: {resp.url}")

            # Tecken's download API currently returns a 200 for HEAD requests
            # when a file exists.
            click.echo(f">>> {method} status code: {resp.status_code}")

            if resp.status_code == 200:
                click.echo(f">>> {method} file size {len(resp.content):,} bytes")


if __name__ == "__main__":
    download_sym_files()
