# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import pathlib
import random

import jsonschema
from molotov import global_setup, setup, scenario


API_URL = "https://symbolication.stage.mozaws.net/symbolicate/v5"
# API_URL = "https://symbolication.services.mozilla.com/symbolicate/v5"
SCHEMA = None
PAYLOADS = []


def load_schema(path):
    schema = json.loads(path.read_text())
    jsonschema.Draft7Validator.check_schema(schema)
    return schema


def load_stack(path):
    return json.loads(path.read_text())


@global_setup()
def system_setup(args):
    """Set up test system.

    This is called before anything runs.

    """
    global SCHEMA
    schema_path = pathlib.Path("../schemas/symbolicate_api_response_v5.json")
    SCHEMA = load_schema(schema_path)
    print("Schema loaded.")

    stacks_dir = pathlib.Path("./stacks/")
    for path in stacks_dir.glob("*.json"):
        path = path.resolve()
        stack = load_stack(path)
        PAYLOADS.append((str(path), stack))
    print(f"Stacks loaded: {len(PAYLOADS)}")
    print(f"Running tests against: {API_URL}")


@setup()
async def worker_setup(worker_id, args):
    """Set the headers.

    NOTE(willkg): The return value is a dict that's passed as keyword arguments
    to aiohttp.ClientSession.

    """
    return {
        "headers": {
            "User-Agent": "tecken-systemtests",
            "Origin": "http://example.com",
        }
    }


@scenario(weight=100)
async def scenario_request_stack(session):
    payload_id = int(random.uniform(0, len(PAYLOADS)))
    payload_path, payload = PAYLOADS[payload_id]
    async with session.post(API_URL, json=payload) as resp:
        assert resp.status == 200, f"failed with {resp.status}: {payload_path}"

        json_data = await resp.json()

        try:
            jsonschema.validate(json_data, SCHEMA)
        except jsonschema.exceptions.ValidationError:
            raise AssertionError("response didn't validate")
