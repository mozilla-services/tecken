# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Resource implementing the Symbolication v4 and v5 APIs.

``debug_filename``
   The original filename the debug symbols are for.

   For example, ``libmozglue.dylib``.

``debug_id``
   When files are compiled, a debug id is generated. This is the debug id.

   For example, ``11FB836EE6723C07BFF775900077457B0``.

``sym_filename``
   This is the symbol filename. Generally, it's the ``debug_filename`` with ``.sym``
   appended except for ``.pdb`` files where ``.sym`` replaces ``.pdb.

   For example, ``libmozglue.dylib.sym``.

"""

from dataclasses import dataclass
import json
import logging
import re
import typing

import falcon

from eliot import downloader
from eliot.libmarkus import METRICS
from eliot.libsymbolic import (
    BadDebugIDError,
    bytes_to_symcache,
    get_module_filename,
    parse_sym_file,
    ParseSymFileError,
    symcache_to_bytes,
)


LOGGER = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    # The filename. e.g. xul.dll on Windows or the same as debug_filename
    filename: str
    # The debug filename. e.g. xul.pdb
    debug_filename: str
    # The debug id for the module
    debug_id: str
    # Whether or not we have a symcache. True/False or None
    has_symcache: typing.Optional[bool]
    # The symbolic symcache instance
    symcache: any


class InvalidModules(Exception):
    pass


class InvalidStacks(Exception):
    pass


# A valid debug id is zero or more hex characters.
VALID_DEBUG_ID = re.compile(r"^([A-Fa-f0-9]*)$")

# A valid debug filename consists of zero or more alpha-numeric characters, some
# punctuation, and spaces.
VALID_DEBUG_FILENAME = re.compile(r"^([A-Za-z0-9_.+{}@<> -]*)$")

# Maximum number of symbolication jobs to do in a single request
MAX_JOBS = 10


def validate_modules(modules):
    """Validate modules and raise an error if invalid

    :arg modules: list of ``[debug_filename, debug_id]`` lists where the debug_id is
        effectively hex and the debug_filename is a library name.

    :raises InvalidModules: if there's a validation problem with the modules

    """
    if not isinstance(modules, list):
        raise InvalidModules("modules must be a list")

    for i, item in enumerate(modules):
        if not isinstance(item, list) or len(item) != 2:
            LOGGER.debug(f"invalid module {item!r}")
            raise InvalidModules(
                f"module index {i} does not have a debug_filename and debug_id"
            )

        debug_filename, debug_id = modules[i]
        if not isinstance(debug_filename, str) or not VALID_DEBUG_FILENAME.match(
            debug_filename
        ):
            LOGGER.debug(f"invalid debug_filename {modules[i]!r}")
            raise InvalidModules(f"module index {i} has an invalid debug_filename")

        if not isinstance(debug_id, str) or not VALID_DEBUG_ID.match(debug_id):
            LOGGER.debug(f"invalid debug_id {modules[i]!r}")
            raise InvalidModules(f"module index {i} has an invalid debug_id")


def validate_stacks(stacks, modules):
    """Stacks is a list of (module index, module offset) integers

    :arg stacks: the stacks that came in the request

    :arg modules: the modules that came in the request

    :raises InvalidStacks: if there's a validation problem with the stacks

    """
    if not isinstance(stacks, list):
        raise InvalidStacks("stacks must be a list of lists")

    if len(stacks) == 0:
        raise InvalidStacks("no stacks specified")

    for i, stack in enumerate(stacks):
        if not isinstance(stack, list):
            LOGGER.debug(f"invalid stack {stack!r}")
            raise InvalidStacks(f"stack {i} is not a list")

        for frame_i, frame in enumerate(stack):
            if not isinstance(frame, list) or len(frame) != 2:
                LOGGER.debug(f"invalid frame {frame!r}")
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} is not a list of two items"
                )

            module_index, module_offset = frame
            if not isinstance(module_index, int):
                LOGGER.debug(f"invalid module_index {frame!r}")
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has an invalid module_index"
                )
            # The module_index is -1 if the memory address isn't in a module and
            # it's an offset in the binary
            if not -1 <= module_index < len(modules):
                LOGGER.debug(f"invalid module_index {frame}")
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has a module_index that isn't in modules"
                )

            if not isinstance(module_offset, int) or module_offset < -1:
                LOGGER.debug(f"invalid module_offset {frame!r}")
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has an invalid module_offset"
                )


class SymbolicateBase:
    def __init__(self, downloader, cache, tmpdir):
        self.downloader = downloader
        self.cache = cache
        self.tmpdir = tmpdir

    def download_sym_file(self, debug_filename, debug_id):
        """Download a symbol file.

        :arg debug_filename: the debug filename
        :arg debug_id: the debug id

        :returns: sym file as bytes or None

        """
        if debug_filename.endswith(".pdb"):
            sym_filename = debug_filename[:-4] + ".sym"
        else:
            sym_filename = debug_filename + ".sym"

        try:
            data = self.downloader.get(debug_filename, debug_id, sym_filename)

        except downloader.FileNotFound:
            return None

        except downloader.ErrorFileNotFound:
            # FIXME(willkg): We probably want to handle this case differently and maybe
            # raise a HTTP 500 because the symbolication request can't be fulfilled.
            # The downloader will capture these issues and at some point, we'll feel
            # stable and can switch this then.
            return None

        return data

    @METRICS.timer_decorator("eliot.symbolicate.parse_sym_file.parse")
    def parse_sym_file(self, debug_filename, debug_id, data):
        """Convert sym file to symcache file

        :arg debug_filename: the debug filename
        :arg debug_id: the debug id
        :arg data: bytes

        :returns: symcache or None

        """
        try:
            return parse_sym_file(debug_filename, debug_id, data, self.tmpdir)

        except BadDebugIDError:
            # If the debug id isn't valid, then there's nothing to parse, so
            # log something, emit a metric, and move on
            LOGGER.error(f"debug_id parse error: {debug_id!r}")
            METRICS.incr(
                "eliot.symbolicate.parse_sym_file.error", tags=["reason:bad_debug_id"]
            )

        except ParseSymFileError as psfe:
            LOGGER.error(f"sym file parse error: {debug_filename} {debug_id!r}")
            METRICS.incr(
                "eliot.symbolicate.parse_sym_file.error",
                tags=[f"reason:{psfe.reason_code}"],
            )

    def get_symcache(self, module_info):
        """Gets the symcache for a given module.

        This uses the cachemanager and downloader to get the symcache. It modifies
        the Module in place.

        :arg module_info: the ModuleInfo data class

        """
        debug_filename = module_info.debug_filename
        debug_id = module_info.debug_id

        if not debug_filename or not debug_id:
            # There isn't anything to get, so mark the module and return this
            module_info.has_symcache = False
            return

        # Get the symcache from cache if it's there
        cache_key = "%s/%s.symc" % (
            debug_filename.replace("/", ""),
            debug_id.upper().replace("/", ""),
        )

        try:
            # Pull it from cache if we can
            data = self.cache.get(cache_key)
            module_info.symcache = bytes_to_symcache(data["symcache"])
            module_info.filename = data["filename"]

        except KeyError:
            # Download the SYM file from one of the sources
            sym_file = self.download_sym_file(debug_filename, debug_id)
            if sym_file is not None:
                # Extract the module filename--this is either debug_filename or
                # pe_filename on Windows
                module_filename = get_module_filename(sym_file, debug_filename)

                # Parse the SYM file into a symcache
                symcache = self.parse_sym_file(debug_filename, debug_id, sym_file)

                # If we have a valid symcache file, cache it to disk
                if symcache is not None:
                    data = symcache_to_bytes(symcache)

                    module_info.symcache = symcache
                    module_info.filename = module_filename

                    data = {"symcache": data, "filename": module_filename}
                    self.cache.set(cache_key, data)

        module_info.has_symcache = module_info.symcache is not None

    def symbolicate(self, stacks, modules):
        """Takes stacks and modules and returns symbolicated stacks.

        :arg stacks: list of stacks each of which is a list of
            (module index, module offset)
        :arg modules: list of (debug_filename, debug_id)

        :returns: dict with "stacks" and "found_modules" keys per the symbolication v5
            response

        """
        # Build list of Module instances so we can keep track of what we've used/seen
        module_records = [
            ModuleInfo(
                filename=debug_filename,
                debug_filename=debug_filename,
                debug_id=debug_id,
                has_symcache=None,
                symcache=None,
            )
            for debug_filename, debug_id in modules
        ]

        symbolicated_stacks = []
        for stack_index, stack in enumerate(stacks):
            METRICS.histogram("eliot.symbolicate.frames_count", value=len(stack))
            symbolicated_stack = []
            for frame_index, frame in enumerate(stack):
                module_index, module_offset = frame
                module_info = None
                data = {
                    "frame": frame_index,
                    "module": "<unknown>",
                    "module_offset": hex(module_offset),
                }

                if module_index >= 0:
                    module_info = module_records[module_index]

                    if module_offset < 0 or module_info.has_symcache is False:
                        # This isn't an offset in this module or there's no symcache
                        # available, so don't do anything
                        pass

                    elif module_info.symcache is None:
                        LOGGER.debug(f"get_symcache for {module_info!r}")
                        # NOTE(willkg): This mutates module
                        self.get_symcache(module_info)

                    if module_info.symcache is not None:
                        lineinfo = module_info.symcache.lookup(module_offset)
                        if lineinfo:
                            # NOTE(willkg): Grab the first in the list. At some point,
                            # we might want to look at the other lines it returns
                            # (inlined functions), but with SYM files, there's only one.
                            lineinfo = lineinfo[0]

                            # FIXME(willkg): do we want symbol or function_name--the
                            # latter is demangled
                            data["function"] = lineinfo.symbol
                            data["function_offset"] = hex(
                                module_offset - lineinfo.sym_addr
                            )
                            if lineinfo.base_dir and lineinfo.filename:
                                data["file"] = "/".join(
                                    [lineinfo.base_dir, lineinfo.filename]
                                )
                            elif lineinfo.filename:
                                data["file"] = lineinfo.filename
                            data["line"] = lineinfo.line

                    data["module"] = module_info.filename

                symbolicated_stack.append(data)

            symbolicated_stacks.append(symbolicated_stack)

        # Convert modules to a map of debug_filename/debug_id -> True/False/None
        # on whether we found the sym file (True), didn't find it (False), or never
        # looked for it (None)
        found_modules = {
            f"{module_info.debug_filename}/{module_info.debug_id}": module_info.has_symcache
            for module_info in module_records
        }

        # Return symbolicated stack
        return {
            "stacks": symbolicated_stacks,
            "found_modules": found_modules,
        }


class SymbolicateV4(SymbolicateBase):
    @METRICS.timer_decorator("eliot.symbolicate.api", tags=["version:v4"])
    def on_post(self, req, resp):
        try:
            payload = json.load(req.bounded_stream)
        except json.JSONDecodeError:
            METRICS.incr("eliot.symbolicate.request_error", tags=["reason:bad_json"])
            raise falcon.HTTPBadRequest(title="Payload is not valid JSON")

        stacks = payload.get("stacks", [])
        modules = payload.get("memoryMap", [])

        try:
            validate_modules(modules)
        except InvalidModules as exc:
            METRICS.incr(
                "eliot.symbolicate.request_error", tags=["reason:invalid_modules"]
            )
            # NOTE(willkg): the str of an exception is the message; we need to
            # control the message carefully so we're not spitting unsanitized data
            # back to the user in the error
            raise falcon.HTTPBadRequest(title=f"job has invalid modules: {exc}")

        try:
            validate_stacks(stacks, modules)
        except InvalidStacks as exc:
            METRICS.incr(
                "eliot.symbolicate.request_error", tags=["reason:invalid_stacks"]
            )
            # NOTE(willkg): the str of an exception is the message; we need to
            # control the message carefully so we're not spitting unsanitized data
            # back to the user in the error
            raise falcon.HTTPBadRequest(title=f"job has invalid stacks: {exc}")

        METRICS.histogram(
            "eliot.symbolicate.stacks_count", value=len(stacks), tags=["version:v4"]
        )

        symdata = self.symbolicate(stacks, modules)

        # Convert the symbolicate output to symbolicate/v4 output
        def frame_to_function(frame):
            if "function" not in frame:
                try:
                    function = hex(frame["module_offset"])
                except TypeError:
                    # Happens if 'module_offset' is not an int16 and thus can't be
                    # represented in hex.
                    function = str(frame["module_offset"])
            else:
                function = frame["function"]
            return "{} (in {})".format(function, frame["module"])

        symbolicated_stacks = [
            [frame_to_function(frame) for frame in stack] for stack in symdata["stacks"]
        ]
        known_modules = [
            symdata["found_modules"].get("%s/%s" % (debug_filename, debug_id), None)
            for debug_filename, debug_id in modules
        ]

        results = {
            "symbolicatedStacks": symbolicated_stacks,
            "knownModules": known_modules,
        }
        resp.text = json.dumps(results)


class SymbolicateV5(SymbolicateBase):
    @METRICS.timer_decorator("eliot.symbolicate.api", tags=["version:v5"])
    def on_post(self, req, resp):
        try:
            payload = json.load(req.bounded_stream)
        except json.JSONDecodeError:
            METRICS.incr("eliot.symbolicate.request_error", tags=["reason:bad_json"])
            raise falcon.HTTPBadRequest(title="Payload is not valid JSON")

        if "jobs" in payload:
            jobs = payload["jobs"]
        else:
            jobs = [payload]

        if len(jobs) > MAX_JOBS:
            METRICS.incr(
                "eliot.symbolicate.request_error", tags=["reason:too_many_jobs"]
            )
            raise falcon.HTTPBadRequest(
                title=f"please limit number of jobs in a single request to <= {MAX_JOBS}"
            )

        METRICS.histogram(
            "eliot.symbolicate.jobs_count", value=len(jobs), tags=["version:v5"]
        )
        LOGGER.debug(f"Number of jobs: {len(jobs)}")

        results = []
        for i, job in enumerate(jobs):
            stacks = job.get("stacks", [])
            modules = job.get("memoryMap", [])

            try:
                validate_modules(modules)
            except InvalidModules as exc:
                METRICS.incr(
                    "eliot.symbolicate.request_error", tags=["reason:invalid_modules"]
                )
                # NOTE(willkg): the str of an exception is the message; we need to
                # control the message carefully so we're not spitting unsanitized data
                # back to the user in the error
                raise falcon.HTTPBadRequest(title=f"job {i} has invalid modules: {exc}")

            try:
                validate_stacks(stacks, modules)
            except InvalidStacks as exc:
                METRICS.incr(
                    "eliot.symbolicate.request_error", tags=["reason:invalid_stacks"]
                )
                # NOTE(willkg): the str of an exception is the message; we need to
                # control the message carefully so we're not spitting unsanitized data
                # back to the user in the error
                raise falcon.HTTPBadRequest(title=f"job {i} has invalid stacks: {exc}")

            METRICS.histogram(
                "eliot.symbolicate.stacks_count", value=len(stacks), tags=["version:v5"]
            )

            results.append(self.symbolicate(stacks, modules))

        resp.text = json.dumps({"results": results})
