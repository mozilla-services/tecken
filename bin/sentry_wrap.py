#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Wraps a command such that if it fails, an error report is sent to the Sentry service
# specified by SENTRY_DSN in the environment.
#
# Usage: python bin/sentry_wrap.py wrap-process -- [CMD]
#    Wraps a process in error-reporting Sentry goodness.
#
# Usage: python bin/sentry_wrap.py test-sentry
#    Tests Sentry configuration and connection.


import os
import shlex
import subprocess
import sys
import time
import traceback

import click
import sentry_sdk
from sentry_sdk import capture_exception, capture_message

from tecken.libdockerflow import get_release_name


def set_up_sentry():
    sentry_dsn = os.environ.get("SENTRY_DSN")

    if not sentry_dsn:
        click.echo("SENTRY_DSN is not defined. Exiting.", err=True)
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)
    release = get_release_name(basedir=base_dir)
    sentry_sdk.init(dsn=sentry_dsn, release=release)


@click.group()
def cli_main():
    pass


@cli_main.command()
@click.pass_context
def test_sentry(ctx):
    set_up_sentry()

    capture_message("Sentry test")
    click.echo("Success. Check Sentry.")


@cli_main.command()
@click.option(
    "--timeout",
    default=300,
    help="Timeout in seconds to wait for process before giving up.",
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    help="Whether to print verbsoe output.",
)
@click.argument("cmd", nargs=-1)
@click.pass_context
def wrap_process(ctx, timeout, verbose, cmd):
    if not cmd:
        raise click.UsageError("CMD required")

    set_up_sentry()

    start_time = time.time()

    cmd = " ".join(cmd)
    cmd_args = shlex.split(cmd)
    if verbose:
        click.echo(f"Running: {cmd_args}")

    try:
        ret = subprocess.run(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        if ret.returncode != 0:
            sentry_sdk.set_context(
                "status",
                {
                    "exit_code": ret.returncode,
                    # Truncate stdout/stderr to the last 5,000 characters in case the
                    # output is monstrously large.
                    "stdout": ret.stdout.decode("utf-8")[-5000:],
                },
            )
            capture_message(f"Command {cmd!r} failed.")
            click.echo(ret.stdout.decode("utf-8"))
            time_delta = (time.time() - start_time) / 1000
            click.echo(f"Command failed. time: {time_delta:.2f}s", err=True)
            ctx.exit(1)

        else:
            click.echo(ret.stdout.decode("utf-8"), nl=False)
            time_delta = (time.time() - start_time) / 1000
            if verbose:
                click.echo(f"Success. time: {time_delta:.2f}s")

    except click.exceptions.Exit:
        raise

    except Exception as exc:
        capture_exception(exc)
        click.echo(traceback.format_exc())
        time_delta = (time.time() - start_time) / 1000
        click.echo(f"Fail. {time_delta:.2f}s")
        ctx.exit(1)


if __name__ == "__main__":
    cli_main()
