#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# List recently generated symbols ZIP files in taskcluster. You can
# use these to do "upload by download url".
#
# Usage: ./bin/list-firefox-symbols-zips.py

import click
import requests


SYMBOLS_ZIP_SUFFIX = ".crashreporter-symbols.zip"
SYMBOLS_FULL_ZIP_SUFFIX = ".crashreporter-symbols-full.zip"
INDEX = "https://firefox-ci-tc.services.mozilla.com/api/index/v1/"
QUEUE = "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/"
NAMESPACE = "gecko.v2.mozilla-central.revision.REV.firefox"

HTTP_HEADERS = {"User-Agent": "tecken-systemtests"}


def index_namespaces(namespace, limit=1000):
    url = INDEX + "namespaces/" + namespace
    resp = requests.post(url, headers=HTTP_HEADERS, json={"limit": limit})
    for namespace in resp.json()["namespaces"]:
        yield namespace["namespace"]


def index_tasks(namespace, limit=1000):
    url = INDEX + "tasks/" + namespace
    r = requests.post(url, headers=HTTP_HEADERS, json={"limit": limit})
    for t in r.json()["tasks"]:
        yield t["taskId"]


def tasks_by_changeset(revisions_limit):
    prefix, suffix = NAMESPACE.split(".REV")
    for namespace in index_namespaces(prefix, revisions_limit):
        full_namespace = namespace + suffix
        for taskid in index_tasks(full_namespace):
            yield taskid


def list_artifacts(taskid):
    url = QUEUE + "task/%s/artifacts" % taskid
    resp = requests.get(url, headers=HTTP_HEADERS)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return [artifact["name"] for artifact in data["artifacts"]]


def get_symbols_urls():
    for taskid in tasks_by_changeset(10):
        artifacts = list_artifacts(taskid)
        full_zip = [a for a in artifacts if a.endswith(SYMBOLS_FULL_ZIP_SUFFIX)]
        if full_zip:
            yield QUEUE + "task/%s/artifacts/%s" % (taskid, full_zip[0])
        else:
            nonfull_zip = [a for a in artifacts if a.endswith(SYMBOLS_ZIP_SUFFIX)]
            if nonfull_zip:
                yield QUEUE + "task/%s/artifacts/%s" % (taskid, nonfull_zip[0])


def get_content_length(url):
    """Gets the content length for the resource at a given url.

    :param url: the url in question

    :returns: content length as an int

    """
    response = requests.head(url, headers=HTTP_HEADERS)
    if response.status_code > 300 and response.status_code < 400:
        return get_content_length(response.headers["location"])
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
def run(number, max_size):
    for url in get_symbols_urls():
        if number <= 0:
            break

        # Get the size and see if it's lower than our max size and also
        # not insane--a 22 byte zip file is just the header
        size = get_content_length(url)
        if 1_000 > size > max_size:
            continue

        print("%s" % url)
        number -= 1


if __name__ == "__main__":
    run()
