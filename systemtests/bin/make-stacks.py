#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Fetches processed crash data for given crash ids and generates
# stacks for use with the Symbolication API. This has two modes:
#
# * print: prints the stack for a single crash id to stdout
# * save: saves one or more stacks for specified crash ids to the file
#   system
#
# Usage: ./bin/make-stacks.py print [CRASHID]
#
# Usage: ./bin/make-stacks.py save [OUTPUTDIR] [CRASHID] [CRASHID...]

import json
import os
import sys

import click
import requests


PROCESSED_CRASH_API = "https://crash-stats.mozilla.org/api/ProcessedCrash"


def fetch_crash_report(crashid):
    """Fetch processed crash data from crash-stats

    :param crashid: the crash id

    :returns: processed crash as a dict

    """
    headers = {"User-Agent": "tecken-systemtests"}
    resp = requests.get(
        PROCESSED_CRASH_API, params={"crash_id": crashid}, headers=headers
    )
    resp.raise_for_status()
    return resp.json()


def build_stack(data):
    """Convert processed crash to a Symbolicate API payload

    :param data: the processed crash as a dict

    :returns: Symbolicate API payload

    """
    json_dump = data.get("json_dump", {})
    if not json_dump:
        return {}

    crashing_thread = json_dump.get("crashing_thread", {})
    if not crashing_thread:
        return {}

    modules = []
    modules_list = []
    for module in json_dump.get("modules", []):
        debug_file = module.get("debug_file", "")
        debug_id = module.get("debug_id", "")

        # Add the module information to the map
        modules.append((debug_file, debug_id))
        # Keep track of which modules are at which index
        modules_list.append(module["filename"])

    stack = []
    for frame in crashing_thread.get("frames", []):
        if "module" in frame:
            module_index = modules_list.index(frame["module"])
        else:
            # -1 indicates the module is unknown
            module_index = -1
        if "module_offset" in frame:
            module_offset = int(frame["module_offset"], base=16)
        else:
            # -1 indicates the module_offset is unknown
            module_offset = -1
        stack.append((module_index, module_offset))

    return {
        "stacks": [stack],
        "memoryMap": modules,
        # NOTE(willkg): we mark this as version 5 so we can use curl on the
        # json files directly
        "version": 5,
    }


@click.group()
def make_stacks_group():
    """Generate stacks for symbolication from existing processed crash data."""


@make_stacks_group.command("print")
@click.option(
    "--pretty/--no-pretty", default=False, help="Whether or not to print it pretty."
)
@click.argument("crashid", nargs=1)
@click.pass_context
def make_stacks_print(ctx, pretty, crashid):
    """Generate a stack from a processed crash and print it to stdout."""
    crashid = crashid.strip()
    crash_report = fetch_crash_report(crashid)
    stack = build_stack(crash_report)
    if pretty:
        kwargs = {"indent": 2}
    else:
        kwargs = {}
    print(json.dumps(stack, **kwargs))


@make_stacks_group.command("save")
@click.argument("outputdir")
@click.argument("crashids", nargs=-1)
@click.pass_context
def make_stacks_save(ctx, outputdir, crashids):
    """Generate stacks from processed crashes and save to file-system."""
    # Handle crash ids from stdin or command line
    if not crashids and not sys.stdin.isatty():
        crashids = list(click.get_text_stream("stdin").readlines())

    if not crashids:
        raise click.BadParameter(
            "No crashids provided.", ctx=ctx, param="crashids", param_hint="crashids"
        )

    if not os.path.exists(outputdir):
        raise click.BadParameter(
            "Outputdir does not exist.",
            ctx=ctx,
            param="outputdir",
            param_hint="outputdir",
        )

    print("Creating stacks and saving them to '%s'..." % outputdir)
    for crashid in crashids:
        crashid = crashid.strip()
        if crashid.startswith("#"):
            continue

        print("%s..." % crashid)
        crash_report = fetch_crash_report(crashid)
        try:
            data = build_stack(crash_report)
        except Exception as exc:
            print(f"Exception thrown: {exc!r}")
            data = None

        if not data or not data["stacks"][0]:
            print("Nothing to save.")
            continue
        with open(os.path.join(outputdir, "%s.json" % crashid), "w") as fp:
            json.dump(data, fp, indent=2)

    print("Done!")


if __name__ == "__main__":
    make_stacks_group()
