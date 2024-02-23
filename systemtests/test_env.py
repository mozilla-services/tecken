#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import click

from systemtests.bin.download_sym_files import download_sym_files
from systemtests.bin.list_firefox_symbols_zips import list_firefox_symbols_zips
from systemtests.bin.upload_symbols import upload_symbols
from systemtests.bin.upload_symbols_by_download import upload_symbols_by_download

ZIPS_DIR = "./data/zip-files/"
USAGE = "Usage: test_env.py [local|stage|prod]"


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
    * STAGE_AUTH_TOKEN
    * PROD_AUTH_TOKEN
    """
    destructive_tests = 0
    bad_token_test = 0
    tecken_host = ""
    auth_token = ""

    try:
        if env == "local":
            destructive_tests = 1
            bad_token_test = 1
            tecken_host = "http://web:8000/"
            auth_token = os.environ["LOCAL_AUTH_TOKEN"]
        elif env == "stage":
            destructive_tests = 1
            bad_token_test = 1
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
    except KeyError:
        raise click.UsageError(f"Token for {env} is not set.") from KeyError

    click.echo(click.style(f"tecken_host: {tecken_host}\n", fg="yellow"))

    # DESTRUCTIVE TESTS
    if destructive_tests == 1:
        click.echo(click.style(">>> UPLOAD TEST (DESTRUCTIVE)", fg="yellow"))
        for fn in [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}{name}")
        ]:
            ctx.invoke(
                upload_symbols,
                expect_code=201,
                auth_token=f"{auth_token}",
                base_url=f"{tecken_host}",
                symbolsfile=f"{ZIPS_DIR}{fn}",
            )

        click.echo(
            click.style(">>> UPLOAD BY DOWNLOAD TEST (DESTRUCTIVE)", fg="yellow")
        )
        URL = ctx.invoke(list_firefox_symbols_zips, number=1, max_size=1000000000)[0]
        ctx.invoke(
            upload_symbols_by_download,
            base_url=f"{tecken_host}",
            auth_token=f"{auth_token}",
            url=f"{URL}",
        )
        print("\n")
    else:
        click.echo(click.style(">>> SKIPPING DESTRUCTIVE TESTS\n", fg="yellow"))

    if bad_token_test == 1:
        # This tests a situation that occurs when nginx is a reverse-proxy to
        # tecken and doesn't work in the local dev environment. bug 1655944
        click.echo(
            click.style(
                ">>> UPLOAD WITH BAD TOKEN TEST--this should return a 403 and error and not a RemoteDisconnected",
                fg="yellow",
            )
        )
        first_file = [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}{name}")
        ][0]
        ctx.invoke(
            upload_symbols,
            expect_code=403,
            auth_token="badtoken",
            base_url=f"{tecken_host}",
            symbolsfile=f"{ZIPS_DIR}{first_file}",
        )

    print("\n")

    click.echo(click.style(">>> DOWNLOAD TEST", fg="yellow"))
    ctx.invoke(
        download_sym_files,
        base_url=f"{tecken_host}",
        csv_file="./data/sym_files_to_download.csv",
    )
    print("\n")


if __name__ == "__main__":
    test_env()
