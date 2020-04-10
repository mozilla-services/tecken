#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Upload symbols to Tecken using the upload API.

# Usage: ./bin/upload-symbols.py FILE

import os
from urllib.parse import urljoin

import click
import markus
from markus.backends import BackendBase
import requests


# Maximum number of retry attempts
MAX_ATTEMPTS = 5

# Number of seconds to wait for a response from server
CONNECTION_TIMEOUT = 60


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
@click.argument("symbolsfile")
@click.pass_context
def upload_symbols(ctx, base_url, auth_token, symbolsfile):
    """Upload SYM files to a host."""

    if not os.path.exists(symbolsfile):
        raise click.BadParameter(
            "Symbols file does not exist.",
            ctx=ctx,
            param="symbolsfile",
            param_hint="symbolsfile",
        )

    url = urljoin(base_url, "/upload/")
    basename = os.path.basename(symbolsfile)

    # This is an upload and it's success is partially dependent on the
    # connection's upload bandwidth. Because it's run in a local dev
    # environment, it's entirely possible uploading will fail periodically.
    # Given that, we wrap uploading in a retry loop.
    success = False
    for i in range(MAX_ATTEMPTS):
        click.echo(
            click.style(
                "Uploading %s to %s (%s/%s) ..."
                % (symbolsfile, url, i + 1, MAX_ATTEMPTS),
                fg="yellow",
            )
        )
        try:
            with METRICS.timer("upload_time"):
                with open(symbolsfile, "rb") as fp:
                    resp = requests.post(
                        url,
                        files={basename: fp},
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
    upload_symbols()
