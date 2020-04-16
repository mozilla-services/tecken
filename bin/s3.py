# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Manipulate emulated S3 storage.

# Usage: ./bin/s3.py CMD


from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import click


def get_client(url):
    parsed = urlparse(url)
    endpoint_url = "%s://%s" % (parsed.scheme, parsed.netloc)

    options = {
        "config": Config(read_timeout=5, connect_timeout=5),
        "endpoint_url": endpoint_url,
    }
    session = boto3.session.Session()
    return session.client("s3", **options)


def get_bucket_name(url):
    parsed = urlparse(url)
    return parsed.path[1:]


@click.group()
def s3_group():
    """Local dev environment S3 manipulation script and bargain emporium."""


@s3_group.command("create")
@click.argument("url")
@click.pass_context
def create_bucket(ctx, url):
    client = get_client(url)
    bucket = get_bucket_name(url)

    try:
        client.head_bucket(Bucket=bucket)
        click.echo('S3 bucket "%s" exists.' % url)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        click.echo('S3 bucket "%r" created.' % url)


@s3_group.command("delete")
@click.argument("url")
@click.pass_context
def delete_buckets(ctx, url):
    client = get_client(url)
    bucket = get_bucket_name(url)

    try:
        client.head_bucket(Bucket=bucket)
        client.delete_bucket(Bucket=bucket)
        click.echo('S3 bucket "%s" deleted.' % url)
    except ClientError:
        click.echo('S3 bucket "%s" does not exist.' % url)


if __name__ == "__main__":
    s3_group()
