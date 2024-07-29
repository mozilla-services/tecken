# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime
import logging
import os
import random
from tempfile import NamedTemporaryFile
import textwrap
from typing import BinaryIO, Iterable, Optional
from urllib.parse import quote
import zipfile

from google.auth import load_credentials_from_file
from google.cloud import storage


LOGGER = logging.getLogger(__name__)

# This prefix is used for all file names. This makes it possible to delete
# all systems test files for a Tecken server, or to create a lifecycle rule
# on a storage bucket to make these files expire quickly.
FILE_NAME_PREFIX = "tecken-system-tests-"


class Random(random.Random):
    def hex_str(self, length: int) -> str:
        return self.randbytes((length + 1) // 2)[:length].hex()


class FakeSymFile:
    DEBUG_FILE_EXTENSIONS = {
        "linux": ".so",
        "mac": ".dylib",
        "windows": ".pdb",
    }
    NONSENSE_DIRECTIVES = [
        "FLIBBERWOCK",
        "ZINDLEFUMP",
        "GRUMBLETOCK",
        "SNORFLEQUIN",
        "WIBBLESNATCH",
        "BLORPTANGLE",
    ]

    def __init__(self, size: int, platform: str, seed: Optional[int] = None):
        self.size = size
        self.platform = platform
        self.seed = seed or random.getrandbits(64)

        rng = Random(self.seed)
        self.arch = rng.choice(["aarch64", "x86", "x86_64"])
        self.debug_id = rng.hex_str(33).upper()
        self.debug_file = (
            FILE_NAME_PREFIX
            + rng.hex_str(16)
            + self.DEBUG_FILE_EXTENSIONS[self.platform]
        )
        self.sym_file = self.debug_file.removesuffix(".pdb") + ".sym"
        if self.platform == "windows":
            self.code_file = self.debug_file.removesuffix(".pdb") + ".dll"
        else:
            self.code_file = ""
        self.code_id = rng.hex_str(16).upper()
        self.build_id = datetime.now().strftime("%Y%m%d%H%M%S")

    def key(self) -> str:
        return f"{self.debug_file}/{self.debug_id}/{self.sym_file}"

    def code_info_key(self) -> str:
        return f"{self.code_file}/{self.code_id}/{self.sym_file}"

    def header(self) -> bytes:
        return textwrap.dedent(f"""\
            MODULE {self.platform} {self.arch} {self.debug_id} {self.debug_file}
            INFO CODE_ID {self.code_id} {self.code_file}
            INFO RELEASECHANNEL nightly
            INFO VERSION 130.0
            INFO VENDOR Mozilla
            INFO PRODUCTNAME Firefox
            INFO BUILDID {self.build_id}
            INFO GENERATOR tecken-system-tests 1.0
            """).encode()

    def write(self, file: BinaryIO):
        header = self.header()
        file.write(header)
        written = len(header)
        rng = Random(self.seed)
        while written < self.size:
            line = f"{rng.choice(self.NONSENSE_DIRECTIVES)} {rng.hex_str(16_384)}\n".encode()
            file.write(line)
            written += len(line)


def _format_file_size(size: int) -> str:
    for factor, unit in [(2**30, "GiB"), (2**20, "MiB"), (2**10, "KiB")]:
        if size >= factor:
            return f"{size / factor:.1f} {unit}"
    return f"{size} bytes"


class FakeZipArchive:
    def __init__(
        self, size: int, sym_file_size: int, platform: str, seed: Optional[int] = None
    ):
        self.size = size
        self.sym_file_size = sym_file_size
        self.platform = platform
        self.seed = seed or random.getrandbits(64)

        self.file_name: Optional[str] = None
        self.members: list[FakeSymFile] = []
        self.uploaded = False

    def create(self, tmp_dir: os.PathLike):
        LOGGER.info(
            "Generating zip archive with a size of %s", _format_file_size(self.size)
        )
        rng = Random(self.seed)
        self.file_name = os.path.join(
            tmp_dir, FILE_NAME_PREFIX + rng.hex_str(16) + ".zip"
        )
        with open(self.file_name, "wb") as f:
            with zipfile.ZipFile(f, "w", compression=zipfile.ZIP_DEFLATED) as zip:
                while f.tell() < self.size:
                    sym_file = FakeSymFile(
                        self.sym_file_size, self.platform, seed=rng.getrandbits(64)
                    )
                    self.members.append(sym_file)
                    with NamedTemporaryFile() as sym_f:
                        sym_file.write(sym_f)
                        zip.write(sym_f.name, sym_file.key())


class FakeDataBucket:
    zip_files_prefix = "zip-files/"
    sym_files_prefix = "sym-files/"
    scratch_prefix = "scratch/"

    def __init__(
        self,
        bucket_name: str,
        public_url: str,
        credentials_path: Optional[os.PathLike] = None,
    ):
        # We want to talk to Google's Cloud storage endpoint, not the emulator
        del os.environ["STORAGE_EMULATOR_HOST"]

        if credentials_path and os.path.exists(credentials_path):
            credentials, _ = load_credentials_from_file(credentials_path)
            client = storage.Client(credentials=credentials)
        else:
            client = storage.Client.create_anonymous_client()
        self.bucket = client.bucket(bucket_name)
        self.public_url = public_url

    def upload_scratch(self, file_name: os.PathLike) -> str:
        base_name = os.path.basename(file_name)
        key = f"{self.scratch_prefix}{base_name}"
        blob = self.bucket.blob(key)
        blob.upload_from_filename(file_name)
        return self.public_url + quote(key)

    def _list_blobs(self, prefix: str, glob: str) -> Iterable[storage.Blob]:
        return self.bucket.list_blobs(prefix=prefix, match_glob=f"{prefix}{glob}")

    def zip_files(self) -> Iterable[storage.Blob]:
        return self._list_blobs(self.zip_files_prefix, "*.zip")

    def sym_files(self) -> Iterable[storage.Blob]:
        return self._list_blobs(self.sym_files_prefix, "*.sym")
