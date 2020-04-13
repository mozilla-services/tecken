#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Upload symbols to Tecken using the upload API.

# Usage: ./bin/upload-symbols-by-download.py

from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase
import requests


# Maximum number of retry attempts
MAX_ATTEMPTS = 5

# Number of seconds to wait for a response from server; this is 3 minutes
# because the server has to do all the work and requests needs to wait for that
# to happen
CONNECTION_TIMEOUT = 180


class StdoutMetrics(BackendBase):
    def emit(self, record):
        click.echo(
            "Elapsed time: %s %s %s" % (record.stat_type, record.key, record.value)
        )


markus.configure([{"class": StdoutMetrics}], raise_errors=True)
METRICS = markus.get_metrics()


@click.command()
@click.option(
    "--base-url",
    default="https://symbols.mozilla.org/",
    help="Base url to use for uploading SYM files.",
)
@click.option(
    "--auth-token", required=True, help="Auth token for uploading SYM files.",
)
@click.argument("url")
@click.pass_context
def upload_symbols_by_download(ctx, base_url, auth_token, url):
    """Upload SYM file to a host using a download url."""

    api_url = urljoin(base_url, "/upload/")

    # It's possible this can fail, so we put it in a retry loop.
    success = False
    for i in range(MAX_ATTEMPTS):
        click.echo(
            click.style(
                "Uploading %s to %s (%s/%s) ..." % (url, api_url, i + 1, MAX_ATTEMPTS),
                fg="yellow",
            )
        )
        try:
            with METRICS.timer("upload_time"):
                resp = requests.post(
                    api_url,
                    data={"url": url},
                    headers={"auth-token": auth_token},
                    timeout=CONNECTION_TIMEOUT,
                )
                if resp.status_code != 201:
                    click.echo(
                        click.style(
                            "Error: %s %s" % (resp.status_code, resp.content), fg="red"
                        )
                    )
                else:
                    success = True
                    click.echo(click.style("Success! %r" % resp.json(), fg="green"))
                    break
        except Exception as exc:
            click.echo(click.style("Error: %s" % exc, fg="red"))

    if not success:
        click.echo(click.style("Error: Max retry attempts reached.", fg="red"))


if __name__ == "__main__":
    upload_symbols_by_download()
