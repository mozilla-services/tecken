#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Upload symbols to Tecken using the upload API.

# Usage: ./bin/upload-symbols.py FILE

import os
import time
from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase
import requests


# Maximum number of retry attempts
MAX_ATTEMPTS = 5

# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 60

# Number of seconds to sleep between tries to account for rate limiting
SLEEP_TIMEOUT = 10


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
@click.option(
    "--expect-code",
    required=False,
    default=201,
    type=int,
    help="The expected response status code.",
)
@click.argument("symbolsfile")
@click.pass_context
def upload_symbols(ctx, base_url, auth_token, symbolsfile, expect_code):
    """Upload SYM file to a host."""

    if not os.path.exists(symbolsfile):
        raise click.BadParameter(
            "Symbols file does not exist.",
            ctx=ctx,
            param="symbolsfile",
            param_hint="symbolsfile",
        )

    api_url = urljoin(base_url, "/upload/")
    headers = {"auth-token": auth_token, "User-Agent": "tecken-systemtests"}
    basename = os.path.basename(symbolsfile)

    # This is an upload and it's success is partially dependent on the
    # connection's upload bandwidth. Because it's run in a local dev
    # environment, it's entirely possible uploading will fail periodically.
    # Given that, we wrap uploading in a retry loop.
    for i in range(MAX_ATTEMPTS):
        click.echo(
            click.style(
                "Uploading %s to %s (%s/%s) ..."
                % (symbolsfile, api_url, i + 1, MAX_ATTEMPTS),
                fg="yellow",
            )
        )
        try:
            with METRICS.timer("upload_time"):
                with open(symbolsfile, "rb") as fp:
                    resp = requests.post(
                        api_url,
                        files={basename: fp},
                        headers=headers,
                        timeout=CONNECTION_TIMEOUT,
                    )

                click.echo(
                    click.style(
                        "Response: %s %r" % (resp.status_code, resp.content),
                        fg="yellow",
                    )
                )

                if resp.status_code == 403:
                    # 403 means the auth token is bad which is not a retryable error
                    if resp.status_code == expect_code:
                        click.echo(click.style("Success! %r" % resp.json(), fg="green"))
                        return
                    else:
                        ctx.exit(1)
                elif resp.status_code == 429:
                    # 429 means we've been rate-limited, so wait and retry
                    click.echo(
                        click.style("429--sleeping for %s" % SLEEP_TIMEOUT, fg="yellow")
                    )
                    time.sleep(SLEEP_TIMEOUT)
                else:
                    if resp.status_code == expect_code:
                        # This is the expected status code, so this is a success
                        click.echo(click.style("Success!", fg="green"))
                        return

                    click.echo(
                        click.style(
                            "Error: %s %s" % (resp.status_code, resp.content), fg="red"
                        )
                    )
                    continue
        except Exception as exc:
            click.echo(click.style("Unexpected error: %s" % exc, fg="red"))

    # We've retried multiple times and never hit the expected status code, so
    # this is a fail
    click.echo(click.style("Error: Max retry attempts reached.", fg="red"))
    ctx.exit(1)


if __name__ == "__main__":
    upload_symbols()
