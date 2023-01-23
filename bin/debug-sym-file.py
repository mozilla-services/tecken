#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Prints information about a sym file including whether it kicks up
# a parse error.

# Usage: debug-sym-file.py [SYMFILE]

import os
import time

import click
import symbolic


@click.command()
@click.argument("symfile")
@click.pass_context
def sym_file_debug(ctx, symfile):
    """Prints information about a sym file including whether it parses correctly."""
    # Print size
    stats = os.stat(symfile)
    click.echo(f"{symfile}")
    click.echo(f"size: {stats.st_size:,}")

    # Print header
    with open(symfile, "r") as fp:
        for line in fp.readlines():
            line = line.strip()
            if line.startswith(("MODULE", "INFO")):
                print(f"header: {line}")
            else:
                break

    # Parse with symbolic and create symcache
    try:
        click.echo("parsing with symbolic ...")
        archive = symbolic.Archive.open(symfile)
        click.echo("listing objects and making symcaches ...")
        for obj in archive.iter_objects():
            click.echo(f"* {obj.debug_id = } ", nl=False)
            start_time = time.time()
            obj.make_symcache()
            delta = time.time() - start_time
            click.echo(f"{delta:.3f}ms")
    except Exception:
        click.echo("symbolic can't parse it")
        raise


if __name__ == "__main__":
    sym_file_debug()
