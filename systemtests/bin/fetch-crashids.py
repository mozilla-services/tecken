#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Fetch crash ids for Firefox nightly from Crash Stats.
#
# Usage: ./bin/fetch-crashids.py

from urllib.parse import urljoin

import click
import requests


CRASHSTATS = "https://crash-stats.mozilla.org/"
MAX_PAGE = 1000

# Indicators that the crash report probably doesn't have a good stack for
# symbolication
MEH_INDICATORS = [
    "IPCError",
    ".dll",
    ".so",
]


def is_meh(signature):
    for indicator in MEH_INDICATORS:
        if indicator in signature:
            return True

    return False


def fetch_supersearch(url, params):
    headers = {"User-Agent": "tecken-systemtests"}
    # Set up first page
    params["_results_offset"] = 0
    params["_results_number"] = MAX_PAGE

    crashids_count = 0
    while True:
        resp = requests.get(url=url, params=params, headers=headers)
        hits = resp.json()["hits"]

        for hit in hits:
            yield hit

        # If there are no more crash ids to get, we return
        total = resp.json()["total"]
        if not hits or crashids_count >= total:
            return

        # Get the next page, but only as many results as we need
        params["_results_offset"] += MAX_PAGE
        params["_results_number"] = min(
            # MAX_PAGE is the maximum we can request
            MAX_PAGE,
            # The number of results Super Search can return to us that is
            # hasn't returned so far
            total - crashids_count,
        )


@click.command()
@click.option(
    "--debug/--no-debug", default=False, help="Show debug output.",
)
@click.option(
    "--num-results", default=10, type=int, help="Number of crash ids to return.",
)
@click.pass_context
def fetch_crashids(ctx, debug, num_results):
    params = {
        "product": "Firefox",
        "release_channel": "nightly",
        "_columns": ["uuid", "signature"],
        "_sort": ["-date"],
    }
    url = urljoin(CRASHSTATS, "/api/SuperSearch/")

    crashids = 0
    for result in fetch_supersearch(url=url, params=params):
        # Skip crash reports that probably have meh stacks
        if is_meh(result["signature"]):
            continue

        if debug:
            print(result)
        else:
            print(result["uuid"])

        crashids += 1
        if crashids > num_results:
            break


if __name__ == "__main__":
    fetch_crashids()
