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
def test_env(env):
    """
    Runs through downloading and uploading tests.

    To use:
    1. run "make shell" to get a shell in the container
    2. then do "cd systemtests"
    3. run "./test_env.py [ENV]"

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
            auth_token = f"{os.environ['LOCAL_AUTH_TOKEN']}"
        elif env == "stage":
            destructive_tests = 1
            bad_token_test = 1
            tecken_host = "https://symbols.stage.mozaws.net/"
            auth_token = f"{os.environ['STAGE_AUTH_TOKEN']}"
        elif env == "prod":
            print("Running tests in prod--skipping destructive tests!")
            tecken_host = "https://symbols.mozilla.org/"
            auth_token = f"{os.environ['PROD_AUTH_TOKEN']}"
        else:
            print(f"{USAGE}")
    except Exception as exc:
        print(f"Unexpected error: {exc}")

    print(f"tecken_host: {tecken_host}\n")

    # DESTRUCTIVE TESTS
    if destructive_tests == 1:
        print(">>> UPLOAD TEST (DESTRUCTIVE)")
        for fn in [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}{name}")
        ]:
            upload_symbols(
                [
                    "--expect-code",
                    201,
                    "--auth-token",
                    f"{auth_token}",
                    "--base-url",
                    f"{tecken_host}",
                    f"{ZIPS_DIR}{fn}",
                ],
                standalone_mode=False,
            )

        print(">>> UPLOAD BY DOWNLOAD TEST (DESTRUCTIVE)")
        URL = list_firefox_symbols_zips(
            ["--number", 1, "--max-size", 1000000000], standalone_mode=False
        )[0]
        upload_symbols_by_download(
            ["--base-url", f"{tecken_host}", "--auth-token", f"{auth_token}", f"{URL}"],
            standalone_mode=False,
        )
        print("\n")
    else:
        print(">>> SKIPPING DESTRUCTIVE TESTS\n")

    if bad_token_test == 1:
        # This tests a situation that occurs when nginx is a reverse-proxy to
        # tecken and doesn't work in the local dev environment. bug 1655944
        print(
            ">>> UPLOAD WITH BAD TOKEN TEST--this should return a 403 and error and not a RemoteDisconnected"
        )
        first_file = [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}{name}")
        ][0]
        print(first_file)
        upload_symbols(
            [
                "--expect-code",
                403,
                "--auth-token",
                "badtoken",
                "--base-url",
                f"{tecken_host}",
                f"{ZIPS_DIR}{first_file}",
            ],
            standalone_mode=False,
        )

    print("\n")

    print(">>> DOWNLOAD TEST")
    download_sym_files(
        [
            "--base-url",
            f"{tecken_host}",
            "./data/sym_files_to_download.csv",
        ],
        standalone_mode=False,
    )
    print("\n")


if __name__ == "__main__":
    test_env()
