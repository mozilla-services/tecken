#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Sends a stack for symbolication with a Symbols server using the
# Symbolicate API.

# Usage: ./bin/symbolicate.py FILE

import json
import os
import sys

import click
import jsonschema
import requests


def load_schema(path):
    with open(path) as fp:
        schema = json.load(fp)
    jsonschema.Draft7Validator.check_schema(schema)
    return schema


class RequestError(Exception):
    pass


def request_stack(url, payload, api_version, is_debug):
    headers = {"User-Agent": "teckent-systemtests"}

    if api_version == 4:
        # We have to add the version to the payload, so parse it, add it, and then
        # unparse it.
        payload["version"] = 4

    options = {}
    if is_debug:
        headers["Debug"] = "true"

    resp = requests.post(url, headers=headers, json=payload, **options)
    if is_debug:
        click.echo(click.style(f"Response: {resp.status_code} {resp.reason}"))
        for key, val in resp.headers.items():
            click.echo(click.style(f"{key}: {val}"))

    if resp.status_code != 200:
        # The server returned something "bad", so print out the things that
        # would be helpful in debugging the issue.
        click.echo(
            click.style("Error: Got status code %s" % resp.status_code, fg="yellow")
        )
        click.echo(click.style("Request payload:", fg="yellow"))
        click.echo(payload)
        click.echo(click.style("Response:", fg="yellow"))
        click.echo(resp.content)
        raise RequestError()

    return resp.json()


@click.group()
def symbolicate_group():
    """Symbolicate stack data."""


@symbolicate_group.command("print")
@click.option(
    "--api-url",
    default="https://symbols.mozilla.org/symbolicate/v4",
    help="The API url to use.",
)
@click.option(
    "--api-version",
    default=4,
    type=int,
    help="The API version to use; 4 or 5; defaults to 4.",
)
@click.option(
    "--debug/--no-debug", default=False, help="Whether to include debug info."
)
@click.argument("stackfile", required=False)
@click.pass_context
def print_stack(ctx, api_url, api_version, debug, stackfile):
    if not stackfile and not sys.stdin.isatty():
        data = click.get_text_stream("stdin").read()

    else:
        if not os.path.exists(stackfile):
            raise click.BadParameter(
                "Stack file does not exist.",
                ctx=ctx,
                param="stackfile",
                param_hint="stackfile",
            )

        with open(stackfile) as fp:
            data = fp.read()

    if api_version not in [4, 5]:
        raise click.BadParameter(
            "Not a valid API version number. Must be 4 or 5.",
            ctx=ctx,
            param="api_version",
            param_hint="api_version",
        )

    try:
        payload = json.loads(data)
    except json.decoder.JSONDecodeError as jde:
        click.echo("Error: request is not valid JSON: %r\n%r" % (jde, data))
        return

    response_data = request_stack(api_url, payload, api_version, debug)
    if debug:
        click.echo(json.dumps(response_data, indent=2))
    else:
        click.echo(json.dumps(response_data))


@symbolicate_group.command("verify")
@click.option(
    "--api-url",
    default="https://symbols.mozilla.org/symbolicate/v4",
    help="The API url to use.",
)
@click.option(
    "--api-version",
    default=4,
    type=int,
    help="The API version to use; 4 or 5; defaults to 4.",
)
@click.argument("stackfile", required=False)
@click.pass_context
def verify_symbolication(ctx, api_url, api_version, stackfile):
    if not stackfile and not sys.stdin.isatty():
        data = click.get_text_stream("stdin").read()

    else:
        if not os.path.exists(stackfile):
            raise click.BadParameter(
                "Stack file does not exist.",
                ctx=ctx,
                param="stackfile",
                param_hint="stackfile",
            )

        with open(stackfile) as fp:
            data = fp.read()

    if api_version not in [4, 5]:
        raise click.BadParameter(
            "Not a valid API version number. Must be 4 or 5.",
            ctx=ctx,
            param="api_version",
            param_hint="api_version",
        )

    if stackfile:
        click.echo(click.style("Working on stackfile %s..." % stackfile, fg="yellow"))
    else:
        click.echo(click.style("Working on stdin...", fg="yellow"))

    payload = json.loads(data)
    response_data = request_stack(api_url, payload, api_version, is_debug=True)

    path = os.path.abspath("../schemas/symbolicate_api_response_v%d.json" % api_version)
    schema = load_schema(path)
    try:
        jsonschema.validate(response_data, schema)
        click.echo(click.style("Response is valid v%s!" % api_version, fg="green"))
    except jsonschema.exceptions.ValidationError as exc:
        click.echo(json.dumps(response_data, indent=2))
        click.echo(
            click.style("Response is invalid v%s! %s" % (api_version, exc), fg="red")
        )
        ctx.exit(1)


if __name__ == "__main__":
    symbolicate_group()
