#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Upload symbols to Tecken using the upload API.

# Usage: ./bin/upload-symbols-by-download.py

import time
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

# Number of seconds to sleep between tries to account for rate limiting
SLEEP_TIMEOUT = 10


class StdoutMetrics(BackendBase):
    def emit(self, record):
        click.echo(
            f"Elapsed time: {record.stat_type} {record.key} {record.value/1000:,.2f}s"
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
    "--auth-token",
    required=True,
    help="Auth token for uploading SYM files.",
)
@click.option(
    "--expect-code",
    required=False,
    default=201,
    type=int,
    help="The expected response status code.",
)
@click.argument("url")
@click.pass_context
def upload_symbols_by_download(ctx, base_url, auth_token, url, expect_code):
    """Upload SYM file to a host using a download url."""

    api_url = urljoin(base_url, "/upload/")
    headers = {"auth-token": auth_token, "User-Agent": "tecken-systemtests"}

    # It's possible this can fail, so we put it in a retry loop.
    for i in range(MAX_ATTEMPTS):
        click.echo(
            click.style(
                f"Uploading {url} to {api_url} ({i+1}/{MAX_ATTEMPTS}) ...",
                fg="yellow",
            )
        )
        try:
            with METRICS.timer("upload_time"):
                resp = requests.post(
                    api_url,
                    data={"url": url},
                    headers=headers,
                    timeout=CONNECTION_TIMEOUT,
                )

                click.echo(
                    click.style(
                        f"Response: {resp.status_code} {resp.content!r}",
                        fg="yellow",
                    )
                )

                if resp.status_code == 403:
                    # 403 means the auth token is bad which is not a retryable error
                    if resp.status_code == expect_code:
                        click.echo(click.style(f"Success! {resp.json()!r}", fg="green"))
                        return
                    else:
                        ctx.exit(1)
                elif resp.status_code == 429:
                    # 429 means we've been rate-limited, so wait and retry
                    click.echo(
                        click.style(f"429--sleeping for {SLEEP_TIMEOUT}", fg="yellow")
                    )
                    time.sleep(SLEEP_TIMEOUT)
                else:
                    if resp.status_code == expect_code:
                        # This is the expected status code, so this is a success
                        click.echo(click.style("Success!", fg="green"))
                        return

                    click.echo(
                        click.style(
                            f"Error: {resp.status_code} {resp.content}", fg="red"
                        )
                    )
                    continue
        except Exception as exc:
            click.echo(click.style(f"Unexpected error: {exc!r}", fg="red"))

    # We've retried multiple times and never hit the expected status code, so
    # this is a fail
    click.echo(click.style("Error: Max retry attempts reached.", fg="red"))
    ctx.exit(1)


if __name__ == "__main__":
    upload_symbols_by_download()
