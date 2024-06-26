# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import os
from typing import Optional
import zipfile
import gzip
import shutil
import logging
import socket

from botocore.exceptions import ClientError
from botocore.vendored.requests.exceptions import ReadTimeout

from django.conf import settings
from django.utils import timezone

from tecken.storage import StorageBucket
from tecken.upload.models import FileUpload, Upload
from tecken.libmarkus import METRICS

logger = logging.getLogger("tecken")


class UnrecognizedArchiveFileExtension(ValueError):
    """Happens when you try to extract a file name we don't know how
    to extract."""


class DuplicateFileDifferentSize(ValueError):
    """When a zip file contains two identically named files whose file size is
    different."""


class SymParseError(Exception):
    """Any kind of error when parsing a sym file."""


def get_file_md5_hash(fn, blocksize=65536):
    hasher = hashlib.md5()
    with open(fn, "rb") as f:
        buf = f.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(blocksize)
    return hasher.hexdigest()


def extract_sym_header_data(file_path):
    """Returns header data from thh sym file header.

    :arg file_path: the path to the sym file

    :returns: sym info as a dict

    :raises SymParseError: any kind of sym parse error

    """
    data = {
        "debug_filename": "",
        "debug_id": "",
        "code_file": "",
        "code_id": "",
        "generator": "",
    }
    with open(file_path, "r") as fp:
        line = "no line yet"
        try:
            for line in fp:
                if line.startswith("MODULE"):
                    parts = line.strip().split()
                    _, opsys, arch, debug_id, debug_filename = parts
                    data["debug_filename"] = debug_filename
                    data["debug_id"] = debug_id.upper()

                elif line.startswith("INFO CODE_ID"):
                    parts = line.strip().split()
                    # NOTE(willkg): Non-Windows module sym files don't have a code_file
                    if len(parts) == 3:
                        _, _, code_id = parts
                        code_file = ""
                    elif len(parts) == 4:
                        _, _, code_id, code_file = parts

                    data["code_file"] = code_file
                    data["code_id"] = code_id.upper()

                elif line.startswith("INFO GENERATOR"):
                    _, _, generator = line.strip().split(maxsplit=2)
                    data["generator"] = generator

                else:
                    break

        except Exception as exc:
            raise SymParseError(f"sym parse error {exc!r} with {line!r}") from exc

    return data


@METRICS.timer_decorator("upload_dump_and_extract")
def dump_and_extract(root_dir, file_buffer, name):
    """Given a directory and an open compressed file and its filename,
    extract all the files in the file and return a list of FileMember
    objects.
    The FileMember objects is only ever files. Not the directories.
    """
    if name.lower().endswith(".zip"):
        zf = zipfile.ZipFile(file_buffer)
        zf.extractall(root_dir)
        namelist = zf.namelist()
        # If there are repeated names in the namelist, dig deeper!
        if len(set(namelist)) != len(namelist):
            # It's only a problem any of the files within are of different size
            sizes = {}
            for info in zf.infolist():
                if info.filename in sizes:
                    if info.file_size != sizes[info.filename]:
                        raise DuplicateFileDifferentSize(
                            "The zipfile buffer contains two files both called "
                            f"{info.filename} and they have difference sizes "
                            "({} != {})".format(info.file_size, sizes[info.filename])
                        )
                sizes[info.filename] = info.file_size
        namelist = set(namelist)

    else:
        raise UnrecognizedArchiveFileExtension(os.path.splitext(name)[1])

    return [
        FileMember(os.path.join(root_dir, filename), filename)
        for filename in namelist
        if os.path.isfile(os.path.join(root_dir, filename))
    ]


class FileMember:
    __slots__ = ["path", "name"]

    def __init__(self, path, name):
        self.path = path
        self.name = name

    @property
    def size(self):
        return os.stat(self.path).st_size

    def __repr__(self):
        return f"<FileMenber {self.path} {self.name}>"


@METRICS.timer_decorator("upload_file_exists")
def key_existing(client, bucket, key):
    """return a tuple of (
        key's size if it exists or 0,
        S3 key metadata
    )
    If the file doesn't exist, return None for the metadata.
    """
    # Return 0 if the key can't be found so the memoize cache can cope
    try:
        response = client.head_object(Bucket=bucket, Key=key)
        return response["ContentLength"], response.get("Metadata")
    except ClientError as exception:
        if exception.response["Error"]["Code"] == "404":
            return 0, None
        raise
    except (ReadTimeout, socket.timeout) as exception:
        logger.info(
            f"ReadTimeout trying to list_objects_v2 for {bucket}:"
            f"{key} ({exception})"
        )
        return 0, None


def should_compressed_key(key_name):
    """Return true if the key name suggests this should be gzip compressed."""
    key_extension = os.path.splitext(key_name)[1].lower()[1:]
    return key_extension in settings.COMPRESS_EXTENSIONS


def is_sym_file(key_name):
    """Return true if it's a symbol file."""
    try:
        key_extension = os.path.splitext(key_name)[1].lower()
        return key_extension == ".sym"
    except IndexError:
        return False


def get_key_content_type(key_name):
    """Return a specific mime type this kind of key name should use, or None"""
    key_extension = os.path.splitext(key_name)[1].lower()[1:]
    return settings.MIME_OVERRIDES.get(key_extension)


@METRICS.timer_decorator("upload_file_upload")
def upload_file_upload(
    backend: StorageBucket,
    key_name: str,
    file_path: str,
    upload: Upload,
) -> Optional[FileUpload]:
    # TODO(jwhitlock): Create StorageBucket API rather than directly use
    # backend clients.
    client = backend.get_storage_client()

    existing_size, existing_metadata = key_existing(client, backend.name, key_name)

    size = os.stat(file_path).st_size

    if not should_compressed_key(key_name):
        # It's easy when you don't have to compare compressed files.
        if existing_size and existing_size == size:
            # Then don't bother!
            METRICS.incr("upload_skip_early_uncompressed", 1)
            return

    metadata = {}
    sym_data = {}
    compressed = False

    if is_sym_file(key_name):
        # If it's a sym file, we want to parse the header to get the debug filename,
        # debug id, code file, and code id to store in the db. We do this before we
        # compress the file.
        try:
            sym_data = extract_sym_header_data(file_path)
        except SymParseError as exc:
            logging.debug("symparseerror: %s", exc)

    if should_compressed_key(key_name):
        compressed = True
        original_size = os.stat(file_path).st_size
        original_md5_hash = get_file_md5_hash(file_path)

        # Before we compress *this* to compare its compressed size with
        # the compressed size in S3, let's first compare the possible
        # metadata and see if it's an opportunity for an early exit.
        existing_metadata = existing_metadata or {}
        if (
            existing_metadata.get("original_size") == str(original_size)
            and existing_metadata.get("original_md5_hash") == original_md5_hash
        ):
            # An upload existed with the exact same original size
            # and the exact same md5 hash.
            # Then we can definitely exit early here.
            METRICS.incr("upload_skip_early_compressed", 1)
            return

        # At this point, we can't exit early by comparing the original.
        # So we're going to have to assume that we'll upload this file.
        metadata["original_size"] = str(original_size)  # has to be string
        metadata["original_md5_hash"] = original_md5_hash

        with METRICS.timer("upload_gzip_payload"):
            with open(file_path, "rb") as f_in:
                with gzip.open(file_path + ".gz", "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                    # Change it from now on to this new file name
                    file_path = file_path + ".gz"
            # The new 'size' is the size of the file after being compressed.
            size = os.stat(file_path).st_size

        if existing_size and existing_size == size and not existing_metadata:
            # This is "legacy fix", but it's worth keeping for at least
            # well into 2018.
            # If a symbol file was (gzipped and) uploaded but without
            # the fancy metadata (see a couple of lines above), then
            # there is one last possibility to compare the size of the
            # exising file in S3 when this local file has been compressed
            # too.
            METRICS.incr("upload_skip_early_compressed_legacy", 1)
            return

    update = bool(existing_size)

    file_upload = FileUpload.objects.create(
        upload=upload,
        bucket_name=backend.name,
        key=key_name,
        update=update,
        compressed=compressed,
        size=size,
        # sym file information
        debug_filename=sym_data.get("debug_filename"),
        debug_id=sym_data.get("debug_id"),
        code_file=sym_data.get("code_file"),
        code_id=sym_data.get("code_id"),
        generator=sym_data.get("generator"),
    )

    content_type = get_key_content_type(key_name)

    # boto3 will raise a botocore.exceptions.ParamValidationError
    # error if you try to do something like:
    #
    #  s3.put_object(Bucket=..., Key=..., Body=..., ContentEncoding=None)
    #
    # ...because apparently 'NoneType' is not a valid type.
    # We /could/ set it to something like '' but that feels like an
    # actual value/opinion. Better just avoid if it's not something
    # really real.
    extras = {}
    if content_type:
        extras["ContentType"] = content_type
    if compressed:
        extras["ContentEncoding"] = "gzip"
    if metadata:
        extras["Metadata"] = metadata

    logger.debug(f"Uploading file {key_name!r} into {backend.name!r}")
    with METRICS.timer("upload_put_object"):
        with open(file_path, "rb") as f:
            client.put_object(Bucket=backend.name, Key=key_name, Body=f, **extras)
    FileUpload.objects.filter(id=file_upload.id).update(completed_at=timezone.now())
    logger.info(f"Uploaded key {key_name}")
    METRICS.incr("upload_file_upload_upload", 1)

    return file_upload
