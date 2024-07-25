#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# List recently generated symbols ZIP files in taskcluster. You can use these to do
# "upload by download url".
#
# Usage: ./bin/list-firefox-symbols-zips.py

import datetime

import click
import requests


SYMBOLS_ZIP_SUFFIX = ".crashreporter-symbols.zip"
SYMBOLS_FULL_ZIP_SUFFIX = ".crashreporter-symbols-full.zip"
INDEX = "https://firefox-ci-tc.services.mozilla.com/api/index/v1/"
QUEUE = "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/"
NAMESPACE = "gecko.v2.mozilla-central.revision.REV.firefox"

HTTP_HEADERS = {"User-Agent": "tecken-smoketests"}


def index_namespaces(namespace, limit=1000):
    # Skip any tasks that were created more than 3 months ago--this makes it more likely
    # we hit a task that has valid symbols zip file that hasn't been deleted
    cutoff = (datetime.date.today() + datetime.timedelta(days=270)).strftime("%Y-%m-%d")

    url = INDEX + "namespaces/" + namespace
    resp = requests.post(url, headers=HTTP_HEADERS, json={"limit": limit})
    for namespace in resp.json()["namespaces"]:
        if namespace["expires"][0:8] < cutoff:
            continue
        yield namespace["namespace"]


def index_tasks(namespace, limit=1000):
    url = INDEX + "tasks/" + namespace
    r = requests.post(url, headers=HTTP_HEADERS, json={"limit": limit})
    for task in r.json()["tasks"]:
        yield task["taskId"]


def tasks_by_changeset(revisions_limit):
    prefix, suffix = NAMESPACE.split(".REV")
    for namespace in index_namespaces(prefix, revisions_limit):
        full_namespace = namespace + suffix
        yield from index_tasks(full_namespace)


def list_artifacts(taskid):
    # Skip any artifacts that have expired
    cutoff = datetime.date.today().strftime("%Y-%m-%d")

    url = QUEUE + f"task/{taskid}/artifacts"
    resp = requests.get(url, headers=HTTP_HEADERS)
    if resp.status_code == 200:
        data = resp.json()
        for artifact in data["artifacts"]:
            if artifact["expires"][0:8] < cutoff:
                continue

            yield artifact["name"]


def get_symbols_urls():
    for taskid in tasks_by_changeset(revisions_limit=10):
        artifacts = list(list_artifacts(taskid))
        full_zip = [
            artifact
            for artifact in artifacts
            if artifact.endswith(SYMBOLS_FULL_ZIP_SUFFIX)
        ]
        if full_zip:
            yield QUEUE + f"task/{taskid}/artifacts/{full_zip[0]}"
        else:
            nonfull_zip = [
                artifact
                for artifact in artifacts
                if artifact.endswith(SYMBOLS_ZIP_SUFFIX)
            ]
            if nonfull_zip:
                yield QUEUE + f"task/{taskid}/artifacts/{nonfull_zip[0]}"


def get_content_length(url):
    """Gets the content length for the resource at a given url.

    :param url: the url in question

    :returns: content length as an int

    :raises requests.exceptions.HTTPError: if the request is forbidden or something

    """
    response = requests.head(url, headers=HTTP_HEADERS)
    if response.status_code > 300 and response.status_code < 400:
        return get_content_length(response.headers["location"])
    response.raise_for_status()
    return int(response.headers["content-length"])


@click.command()
@click.option(
    "--number",
    default=5,
    type=int,
    help="number of urls to print out; don't do more than 100",
)
@click.option(
    "--max-size",
    default=1_000_000_000,
    type=int,
    help="max size of files in bytes for urls to print out",
)
def list_firefox_symbols_zips(number, max_size):
    urls = []
    for url in get_symbols_urls():
        if number <= 0:
            break

        # Get the size and see if it's lower than our max size and also
        # sensible--a 22 byte zip file is just the header
        try:
            size = get_content_length(url)
        except requests.exceptions.HTTPError:
            continue

        if 1_000 > size > max_size:
            continue

        click.echo(url)
        urls.append(url)
        number -= 1

    return urls


if __name__ == "__main__":
    list_firefox_symbols_zips()
