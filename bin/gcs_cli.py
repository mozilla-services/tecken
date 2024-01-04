#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Manipulate emulated GCS storage.

# Usage: ./bin/gcs_cli.py CMD

import os

import click
import requests
import urllib3

from google.auth.credentials import AnonymousCredentials
from google.cloud import storage
from google.cloud.exceptions import NotFound

base_url = os.environ["STORAGE_EMULATOR_HOST"]


def get_client():
    # Create a session that is OK talking over insecure HTTPS
    weak_https = requests.Session()
    weak_https.verify = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return storage.Client(
        credentials=AnonymousCredentials(), project="test", _http=weak_https
    )


@click.group()
def gcs_group():
    """Local dev environment GCS manipulation script"""


@gcs_group.command("create")
@click.argument("bucket_name")
def create_bucket(bucket_name):
    """Creates a bucket

    Specify BUCKET name.

    """
    # https://github.com/fsouza/fake-gcs-server/blob/0c31d1573c14912fc58ae68118f9c9ece266756a/README.md?plain=1#L47
    endpoint_url = f"{base_url}/storage/v1/b/{bucket_name}"

    client = get_client()

    try:
        client.get_bucket(bucket_name)
        click.echo(f"GCS bucket {bucket_name!r} exists in {endpoint_url!r}.")
    except NotFound:
        client.create_bucket(bucket_name)
        click.echo(f"GCS bucket {bucket_name!r} in {endpoint_url!r} created.")


@gcs_group.command("delete")
@click.argument("bucket_name")
def delete_bucket(bucket_name):
    """Deletes a bucket

    Specify BUCKET name.

    """
    # https://github.com/fsouza/fake-gcs-server/blob/0c31d1573c14912fc58ae68118f9c9ece266756a/README.md?plain=1#L47
    endpoint_url = f"{base_url}/storage/v1/b/{bucket_name}"

    client = get_client()

    bucket = None

    try:
        bucket = client.get_bucket(bucket_name)
    except NotFound:
        click.echo(f"GCS bucket {bucket_name!r} at {endpoint_url!r} does not exist.")
        return

    # Delete any objects in the bucket
    blobs = client.list_blobs(bucket_name)
    for blob in blobs:
        click.echo(f"Deleting GCS object {blob.name}...")
        blob.delete()

    # Then delete the bucket
    bucket.delete()
    click.echo(f"GCS bucket {bucket_name!r} at {endpoint_url!r} deleted.")


@gcs_group.command("list_buckets")
@click.option("--details/--no-details", default=True, type=bool, help="With details")
def list_buckets(details):
    """List GCS buckets"""

    client = get_client()

    buckets = client.list_buckets()
    for bucket in buckets:
        if details:
            # https://cloud.google.com/storage/docs/json_api/v1/buckets#resource-representations
            click.echo(f"{bucket.name}\t{bucket.time_created}")
        else:
            click.echo(f"{bucket.name}")


# def list_objects():
# todo
# see client.list_blobs(bucket_name)

if __name__ == "__main__":
    gcs_group()
