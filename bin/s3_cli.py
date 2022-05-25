#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Manipulate emulated S3 storage.

# Usage: ./bin/s3_cli.py CMD

import os
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import click


def get_client(endpoint_url):
    session = boto3.session.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    client = session.client(
        service_name="s3",
        config=Config(s3={"addressing_style": "path"}),
        endpoint_url=endpoint_url,
    )
    return client


def parse_endpoint_url_and_bucket(bucket_or_url):
    """Parse endpoint url and bucket from a string

    This defaults the endpoint_url to AWS_ENDPOINT_URL in the environment if a
    url is not otherwise specified.

    This pulls the bucket name from the url path or assumes the bucket_or_url is
    itself the bucket name.

    :param str bucket_or_url: the string to extract endpoint_url and bucket name from

    :returns: dict with "endpoint_url" and "bucket" keys

    """
    if bucket_or_url.startswith("http"):
        # The bucket value is a url, so we pull it apart into a client endpoint url
        # and a bucket name
        parsed = urlparse(bucket_or_url)
        endpoint_url = f"{parsed.scheme}://{parsed.netloc}"
        path_parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
        if path_parts:
            bucket = path_parts[0]
        else:
            bucket = ""

    else:
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "unknown")
        bucket = bucket_or_url

    return {
        "endpoint_url": endpoint_url,
        "bucket": bucket,
    }


@click.group()
def s3_group():
    """Local dev environment S3 manipulation script and bargain emporium."""


@s3_group.command("create")
@click.argument("bucket")
@click.pass_context
def create_bucket(ctx, bucket):
    """Creates a bucket

    Specify "bucket" as a name or url.

    """
    ret = parse_endpoint_url_and_bucket(bucket)
    endpoint_url = ret["endpoint_url"]
    bucket = ret["bucket"]

    if not bucket:
        raise click.UsageError("No bucket specified.")

    client = get_client(endpoint_url)

    try:
        client.head_bucket(Bucket=bucket)
        click.echo(f"Bucket {bucket!r} exists in {endpoint_url!r}.")
    except ClientError:
        client.create_bucket(Bucket=bucket)
        click.echo(f"Bucket {bucket!r} in {endpoint_url!r} created.")


@s3_group.command("delete")
@click.argument("bucket")
@click.pass_context
def delete_bucket(ctx, bucket):
    """Deletes a bucket

    Specify "bucket" as a name or url.

    """
    ret = parse_endpoint_url_and_bucket(bucket)
    endpoint_url = ret["endpoint_url"]
    bucket = ret["bucket"]

    if not bucket:
        raise click.UsageError("No bucket specified.")

    client = get_client(endpoint_url)

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        click.echo(f"S3 bucket {bucket!r} at {endpoint_url!r} does not exist.")
        return

    # Delete any objects in the bucket
    resp = client.list_objects(Bucket=bucket)
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        click.echo(f"Deleting {key}...")
        client.delete_object(Bucket=bucket, Key=key)

    # Then delete the bucket
    client.delete_bucket(Bucket=bucket)
    click.echo(f"S3 bucket {bucket!r} at {endpoint_url!r} deleted.")


@s3_group.command("list_buckets")
@click.option("--details/--no-details", default=True, type=bool, help="With details")
@click.argument("url", required=False)
@click.pass_context
def list_buckets(ctx, url, details):
    """List S3 buckets

    url can be specified as an endpoint url or a bucket url.

    """
    ret = parse_endpoint_url_and_bucket(url or "")
    endpoint_url = ret["endpoint_url"]

    client = get_client(endpoint_url)

    resp = client.list_buckets()
    for bucket in resp["Buckets"]:
        if details:
            click.echo(f"{bucket['Name']}\t{bucket['CreationDate']}")
        else:
            click.echo(f"{bucket['Name']}")


@s3_group.command("list_objects")
@click.option("--details/--no-details", default=True, type=bool, help="With details")
@click.argument("bucket")
@click.pass_context
def list_objects(ctx, bucket, details):
    """List contents of a bucket"""
    ret = parse_endpoint_url_and_bucket(bucket)
    endpoint_url = ret["endpoint_url"]
    bucket = ret["bucket"]

    if not bucket:
        raise click.UsageError("No bucket specified.")

    client = get_client(endpoint_url)

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        click.echo(f"Bucket {bucket!r} does not exist.")
        return

    resp = client.list_objects_v2(Bucket=bucket)
    contents = resp.get("Contents", [])
    if contents:
        for item in contents:
            if details:
                click.echo(f"{item['Key']}\t{item['Size']}\t{item['LastModified']}")
            else:
                click.echo(f"{item['Key']}")
    else:
        click.echo("No objects in bucket.")


if __name__ == "__main__":
    s3_group()
