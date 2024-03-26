#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Usage: test_env.py [local|stage|prod]"
import os

import click

from systemtests.bin.download_sym_files import download_sym_files
from systemtests.bin.list_firefox_symbols_zips import list_firefox_symbols_zips
from systemtests.bin.upload_symbols import upload_symbols
from systemtests.bin.upload_symbols_by_download import upload_symbols_by_download

ZIPS_DIR = "./data/zip-files/"


@click.command()
@click.argument("env")
@click.pass_context
def test_env(ctx, env):
    """
    Runs through downloading and uploading tests.

    \b
    ENV is the environment to run the tests against;
    one of [local|stage|prod].

    \b
    To use:
    1. run "make shell" to get a shell in the container
    2. then do "cd systemtests"
    3. run "./test_env.py [local|stage|prod]"

    \b
    To set auth tokens, add these to your .env file:
    * LOCAL_AUTH_TOKEN
    * LOCAL_AUTH_TOKEN_TRY
    * STAGE_AUTH_TOKEN
    * STAGE_AUTH_TOKEN_TRY
    * PROD_AUTH_TOKEN

    \b
    Note: Due to Bug 1759740, we need separate auth tokens
    for try uploads with "Upload Try Symbols Files" permissions.
    """
    destructive_tests = False
    bad_token_test = False
    tecken_host = ""
    auth_token = ""

    if env == "local":
        destructive_tests = True
        bad_token_test = True
        tecken_host = "http://web:8000/"
        auth_token = os.environ["LOCAL_AUTH_TOKEN"]
    elif env == "stage":
        destructive_tests = True
        bad_token_test = True
        tecken_host = "https://symbols.stage.mozaws.net/"
        auth_token = os.environ["STAGE_AUTH_TOKEN"]
    elif env == "prod":
        click.echo(
            click.style(
                "Running tests in prod--skipping destructive tests!", fg="yellow"
            )
        )
        tecken_host = "https://symbols.mozilla.org/"
        auth_token = os.environ["PROD_AUTH_TOKEN"]
    else:
        raise click.UsageError("ENV must be one of 'local', 'stage', or 'prod'.")

    click.echo(click.style(f"tecken_host: {tecken_host}\n", fg="yellow"))

    if destructive_tests:
        click.echo(click.style(">>> UPLOAD TEST (DESTRUCTIVE)", fg="yellow"))
        for fn in [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}{name}")
        ]:
            # Use the try upload API token when needed
            if fn.endswith("__try.zip"):
                auth_token = os.environ[f"{env.upper()}_AUTH_TOKEN_TRY"]
            else:
                auth_token = os.environ[f"{env.upper()}_AUTH_TOKEN"]
            ctx.invoke(
                upload_symbols,
                expect_code=201,
                auth_token=auth_token,
                base_url=tecken_host,
                symbolsfile=f"{ZIPS_DIR}{fn}",
            )
        click.echo("")

        click.echo(
            click.style(">>> UPLOAD BY DOWNLOAD TEST (DESTRUCTIVE)", fg="yellow")
        )
        url = ctx.invoke(list_firefox_symbols_zips, number=1, max_size=1000000000)[0]
        ctx.invoke(
            upload_symbols_by_download,
            base_url=tecken_host,
            auth_token=auth_token,
            url=url,
        )
    else:
        click.echo(click.style(">>> SKIPPING DESTRUCTIVE TESTS", fg="yellow"))
    click.echo("")

    if bad_token_test:
        # Pick a zip file that's > 120kb and upload it with a bad token. This tests a
        # situation that occurs when nginx is a reverse-proxy to Tecken and doesn't
        # correctly return a response if the stream isn't exhausted. This doesn't work
        # in the local dev environment. bug #1655944
        click.echo(
            click.style(
                (
                    ">>> UPLOAD WITH BAD AUTH TOKEN TEST--this should return an HTTP "
                    "403 and not a RemoteDisconnected"
                ),
                fg="yellow",
            )
        )
        zip_files = [
            f"{ZIPS_DIR}{name}"
            for name in os.listdir(f"{ZIPS_DIR}")
            if (
                os.path.isfile(f"{ZIPS_DIR}{name}")
                and os.path.getsize(f"{ZIPS_DIR}{name}") > 120_000
            )
        ]

        if not zip_files:
            click.echo(
                click.style(
                    ">>> No zip files > 120kb; skipping bad token test", fg="red"
                )
            )
        else:
            ctx.invoke(
                upload_symbols,
                expect_code=403,
                auth_token="badtoken",
                base_url=tecken_host,
                symbolsfile=zip_files[0],
            )
            click.echo("")

    click.echo(click.style(">>> DOWNLOAD TEST", fg="yellow"))
    ctx.invoke(
        download_sym_files,
        base_url=tecken_host,
        csv_file="./data/sym_files_to_download.csv",
    )


if __name__ == "__main__":
    test_env()
