# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import random
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

from tecken.upload.models import Upload, FileUpload


def make_debug_id():
    """Debug id is a uuid4 hex representation with a u32 appendix

    https://github.com/getsentry/rust-debugid/blob/c0503b86a7b4e7e2177855c0887d450207ea9680/src/lib.rs#L50-L53
    """
    return uuid.uuid4().hex.upper() + "A"


def make_code_id():
    """Code id is a ... I have no idea, so whatever"""
    return uuid.uuid4().hex.upper()[0:15]


def make_debug_info():
    return {
        "debug_filename": "xul.pdb",
        "debug_id": make_debug_id(),
        "code_file": "xul.dll",
        "code_id": make_code_id(),
    }


def chunked(iterable, n):
    group = []
    for i, item in enumerate(iterable):
        if i % n != 0:
            group.append(item)
        elif group:
            yield group
            group = []
    yield group


class Command(BaseCommand):
    help = "Generate fake data (poorly)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email address for account to own uploads.")
        parser.add_argument("numuploads", type=int, help="Number of uploads to create.")

    def handle(self, *args, **options):
        email = options["email"]
        num_uploads = options["numuploads"]

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"Invalid email {email!r}")

        for chunk in chunked(list(range(num_uploads)), 100):
            self.stdout.write(f"working on {chunk[0]}/{num_uploads}...")
            upload_objs = [
                Upload(
                    user=user,
                    filename="target.crashreporter.zip",
                    bucket_name="publicbucket",
                    bucket_endpoint_url="foo",
                    skipped_keys=[],
                    ignored_keys=[],
                    completed_at=timezone.now(),
                    size=random.randint(1000, 100000),
                )
                for item in chunk
            ]
            Upload.objects.bulk_create(upload_objs)

            for upload in upload_objs:
                num_files = random.randint(1, 50)
                objs = []
                for _ in range(num_files):
                    sym_file = "xul.sym"
                    debug_info = make_debug_info()
                    objs.append(
                        FileUpload(
                            upload=upload,
                            bucket_name="publicbucket",
                            key=f"v1/{debug_info['debug_filename']}/{debug_info['debug_id']}/{sym_file}",
                            size=random.randint(1000, 100000),
                            debug_filename=debug_info["debug_filename"],
                            debug_id=debug_info["debug_id"],
                            code_file=debug_info["code_file"],
                            code_id=debug_info["code_id"],
                            generator="generate_fake_data",
                        )
                    )
                FileUpload.objects.bulk_create(objs)
