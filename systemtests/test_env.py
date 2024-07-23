#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Usage: test_env.py [local|stage|prod]"
from dataclasses import dataclass
import os
from pathlib import Path
import textwrap

import click

from systemtests.bin.download_sym_files import download_sym_files
from systemtests.bin.list_firefox_symbols_zips import list_firefox_symbols_zips
from systemtests.bin.upload_symbols import upload_symbols
from systemtests.bin.upload_symbols_by_download import upload_symbols_by_download

ZIP_FILES = list(Path("./data/zip-files").glob("*.zip"))


@dataclass
class Environment:
    # The name of the environment
    name: str

    # The base URL of the Tecken instance to test.
    base_url: str

    # Whether to perform the destructive upload tests.
    destructive_tests: bool

    # Whether to perform the bad token test.
    bad_token_test: bool

    def env_var_name(self, try_storage: bool) -> str:
        env_var_name = self.name.upper() + "_AUTH_TOKEN"
        if try_storage:
            env_var_name += "_TRY"
        return env_var_name

    def help(self) -> str:
        text = textwrap.dedent(f"""
            \b
            {self.name}
            ====
              Base URL: {self.base_url}
              Environment variables:
                * {self.env_var_name(False)}
            """)
        if self.destructive_tests:
            text += f"    * {self.env_var_name(True)}\n"
        return text

    def auth_token(self, try_storage: bool) -> str:
        return os.environ[self.env_var_name(try_storage)]


ENVIRONMENTS = {
    "local": Environment(
        name="local",
        base_url="http://web:8000/",
        destructive_tests=True,
        bad_token_test=True,
    ),
    "stage": Environment(
        name="stage",
        base_url="https://symbols.stage.mozaws.net/",
        destructive_tests=True,
        bad_token_test=True,
    ),
    "prod": Environment(
        name="prod",
        base_url="https://symbols.mozilla.org/",
        destructive_tests=False,
        bad_token_test=False,
    ),
    "gcp_stage": Environment(
        name="gcp_stage",
        base_url="https://tecken-stage.symbols.nonprod.webservices.mozgcp.net/",
        destructive_tests=True,
        bad_token_test=True,
    ),
    "gcp_prod": Environment(
        name="gcp_prod",
        base_url="https://tecken-prod.symbols.prod.webservices.mozgcp.net/",
        destructive_tests=False,
        bad_token_test=False,
    ),
}

ENV_HELP = "\n".join(env.help() for env in ENVIRONMENTS.values())

CLI_HELP = f"""
Runs upload and download tests against the environment specified in ENV_NAME.

Available environments:

{ENV_HELP}

\b
Usage:
1. run "make shell" to get a shell in the container
2. then do "cd systemtests"
3. run "./setup_tests.py" if you are running the tests for the first time.
4. run "./test_env.py [{"|".join(ENVIRONMENTS)}]"

Note: Due to Bug 1759740, we need separate auth tokens
for try uploads with "Upload Try Symbols Files" permissions.
"""


@click.command(help=CLI_HELP)
@click.argument("env_name")
@click.pass_context
def test_env(ctx, env_name):
    try:
        env = ENVIRONMENTS[env_name]
    except KeyError:
        env_names = ", ".join(f"'{name}'" for name in ENVIRONMENTS)
        raise click.UsageError(f"ENV_NAME must be one of {env_names}.") from None

    click.echo(click.style(f"Tecken base URL: {env.base_url}\n", fg="yellow"))

    if env.destructive_tests:
        click.echo(click.style(">>> UPLOAD TEST (DESTRUCTIVE)", fg="yellow"))
        for path in ZIP_FILES:
            try_storage = path.stem.endswith("__try")
            auth_token = env.auth_token(try_storage)
            ctx.invoke(
                upload_symbols,
                expect_code=201,
                auth_token=auth_token,
                base_url=env.base_url,
                symbolsfile=str(path),
            )
        click.echo("")

        click.echo(
            click.style(">>> UPLOAD BY DOWNLOAD TEST (DESTRUCTIVE)", fg="yellow")
        )
        url = ctx.invoke(list_firefox_symbols_zips, number=1, max_size=1_000_000_000)[0]
        ctx.invoke(
            upload_symbols_by_download,
            base_url=env.base_url,
            auth_token=auth_token,
            url=url,
        )
    else:
        click.echo(click.style(">>> SKIPPING DESTRUCTIVE TESTS", fg="yellow"))
    click.echo("")

    if env.bad_token_test:
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
        for path in ZIP_FILES:
            if path.stat().st_size > 120_000:
                ctx.invoke(
                    upload_symbols,
                    expect_code=403,
                    auth_token="badtoken",
                    base_url=env.base_url,
                    symbolsfile=str(path),
                )
                click.echo("")
                break
        else:
            click.echo(
                click.style(
                    ">>> No zip files > 120kb; skipping bad token test", fg="red"
                )
            )

    click.echo(click.style(">>> DOWNLOAD TEST", fg="yellow"))
    ctx.invoke(
        download_sym_files,
        base_url=env.base_url,
        csv_file="./data/sym_files_to_download.csv",
    )


if __name__ == "__main__":
    test_env()
