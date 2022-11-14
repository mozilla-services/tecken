# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Utilities for using symbolic library.
"""

from io import BytesIO
import logging
import os
import tempfile

import symbolic


LOGGER = logging.getLogger(__name__)


def bytes_split_generator(item, sep):
    """Takes a bytes or bytearray and returns a generator of parts split on sep

    :arg item: bytes-like object
    :arg sep: bytes-like object

    :returns: generator splitting the item

    """
    index = 0
    len_item = len(item)

    while index <= len_item:
        next_index = item.find(sep, index)
        if next_index == -1:
            break

        yield item[index:next_index]
        index = next_index + len(sep)


def get_module_filename(sym_file, debug_filename):
    """Returns the module filename

    On Windows, this will be the pe_file in the INFO line:

        INFO CODE_ID xxx pe_file

    On other platforms, this is the debug_filename.

    :arg bytes sym_file: the sym file as bytes
    :arg str debug_filename: the debug filename

    :returns: the module filename

    """
    # Iterate through the first few lines of the file until we hit FILE in which
    # case there's no INFO for some reason or we hit the first INFO.
    for line in bytes_split_generator(sym_file, b"\n"):
        if line.startswith(b"INFO"):
            parts = line.split(b" ")
            if len(parts) == 4:
                return parts[-1].decode("utf-8").strip()
            else:
                break

        elif line.startswith((b"FILE", b"PUBLIC", b"FUNC")):
            break

    return debug_filename


class BadDebugIDError(Exception):
    pass


class ParseSymFileError(Exception):
    """Error thrown when there are problems parsing the sym file

    :arg reason_code: a string denoting a reason code for metrics purposes
    :arg msg: the exception message

    """

    def __init__(self, reason_code, msg):
        super().__init__(f"{reason_code}: {msg}")
        self.reason_code = reason_code


def convert_debug_id(debug_id):
    """Convert a debug_id into a symbolic debug id.

    :arg debug_id: a debug id string; ex: "58C99D979ADA4CD795F8740CE23C2E1F2"

    :returns: debug id formatted the way symbolic likes; ex:
        "58c99d97-9ada-4cd7-95f8-740ce23c2e1f-2"

    :raises BadDebugIDError: if the debug id is invalid

    """
    try:
        return symbolic.normalize_debug_id(debug_id)
    except symbolic.ParseDebugIdError:
        raise BadDebugIDError("invalid_identifier")


def parse_sym_file(debug_filename, debug_id, data, tmpdir):
    """Convert sym file to symcache file

    :arg debug_filename: the debug filename
    :arg debug_id: the debug id
    :arg data: bytes
    :arg tmpdir: the temp directory to use

    :returns: symcache or None

    :raises BadDebugIDError: if the debug_id is invalid

    :raises ParseSymFileError: if the SYM file isn't parseable, doesn't have the debug
        id, or some other problem

    """
    sdebug_id = convert_debug_id(debug_id)

    try:
        temp_fp = tempfile.NamedTemporaryFile(
            mode="w+b", suffix=".sym", dir=tmpdir, delete=False
        )
        try:
            temp_fp.write(data)
            temp_fp.close()
            LOGGER.debug(
                f"created temp file {debug_filename} {debug_id} {temp_fp.name}"
            )
            archive = symbolic.Archive.open(temp_fp.name)
            obj = archive.get_object(debug_id=sdebug_id)
            symcache = obj.make_symcache()

        except LookupError:
            LOGGER.exception(
                f"error looking up debug id in SYM file: {debug_filename} {debug_id}"
            )
            raise ParseSymFileError(
                reason_code="sym_debug_id_lookup_error",
                msg="error looking up debug id in sym file {debug_filename} {debug_id}",
            )

        except (
            symbolic.ObjectErrorUnknown,
            symbolic.ObjectErrorUnsupportedObject,
            symbolic.SymCacheErrorBadDebugFile,
        ):
            # Invalid symcache
            LOGGER.exception(f"error with SYM file: {debug_filename} {debug_id}")
            raise ParseSymFileError(
                reason_code="sym_malformed",
                msg="error with sym file {debug_filename} {debug_id}",
            )

        finally:
            os.unlink(temp_fp.name)

    except OSError as exc:
        LOGGER.exception("error creating tmp file for SYM file")
        raise ParseSymFileError(
            reason_code="sym_tmp_file_error",
            msg=f"error creating tmp file {exc}",
        )

    return symcache


def bytes_to_symcache(data):
    """Convert a bytes into a symcache

    :arg data: the bytes data to convert

    :returns: a symcache instance

    """
    return symbolic.SymCache.from_bytes(data)


def symcache_to_bytes(symcache):
    """Convert a symcache to bytes

    :arg symcache: the symcache instance to convert

    :returns: bytes

    """
    data = BytesIO()
    symcache.dump_into(data)
    return data.getvalue()
