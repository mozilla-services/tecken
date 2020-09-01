#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
This script makes it possible to delete *some* files that have beem
uploaded into Minio. That's useful when you want there to be "holes".

Usually, when you do a load test or sample upload of a zip file, *all*
files it either *don't* exist or all files already *exists*.
By deleting only some, you can get a nice scenario where in a given .zip
upload only some of the files already exists.
"""

from __future__ import print_function  # in case you use Python 2

import os
import random
import boto3


def fmtsize(b):
    if b > 1024 ** 2:
        return "{:.1f}MB".format(b / 1024 / 1024)
    else:
        return "{:.1f}KB".format(b / 1024)


def run(count, directory, bucket, endpoint_url, search=""):
    all = []
    for root, dirs, files in os.walk(os.path.join(directory, bucket)):
        # if '.minio.sys' in root:
        #     continue
        for name in files:
            fn = os.path.join(root, name)
            if search:
                for part in search.split():
                    if part in fn:
                        all.append(fn)
                        break
            else:
                all.append(fn)

    print(len(all), "Possible files found")
    s3 = boto3.client(
        "s3",
        aws_access_key_id="minio",
        aws_secret_access_key="miniostorage",
        endpoint_url=endpoint_url,
    )
    sizes = []
    for fn in random.sample(all, min(len(all), count)):
        size = os.stat(fn).st_size
        print(fmtsize(size).ljust(10), fn)
        sizes.append(size)
        key = fn.replace(directory, "").replace(bucket, "").lstrip("/")
        response = s3.delete_object(
            Bucket=bucket,
            Key=key,
        )
        if response["ResponseMetadata"]["HTTPStatusCode"] != 204:
            raise Exception(response)
    print()
    print(
        "Deleted {} files (of {} possible) totalling {}".format(
            len(sizes),
            len(all),
            fmtsize(sum(sizes)),
        )
    )


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "count",
        help="The number of random files to delete",
        type=int,
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="Where are the files we're going to random delete from",
        default="miniodata",
    )
    parser.add_argument(
        "-b",
        "--bucket",
        help="S3 bucket in Minio",
        default="testbucket",
    )
    parser.add_argument(
        "--endpoint_url",
        help="Endpoint URL for Minio (default http://localhost:9000)",
        default="http://localhost:9000",
    )
    parser.add_argument(
        "-s",
        "--search",
        help="Must match in filename",
        default="",
    )
    args = parser.parse_args()
    return run(
        args.count,
        args.directory,
        args.bucket,
        args.endpoint_url,
        search=args.search,
    )


if __name__ == "__main__":
    import sys

    sys.exit(main())
