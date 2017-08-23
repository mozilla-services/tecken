# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import zipfile
import gzip
import tarfile


class UnrecognizedArchiveFileExtension(ValueError):
    pass


class _ZipMember:

    def __init__(self, member, container):
        self.member = member
        self.container = container

    def extractor(self):
        return self.container.open(self.name)

    @property
    def name(self):
        return self.member.filename

    @property
    def size(self):
        return self.member.file_size


class _TarMember:

    def __init__(self, member, container):
        self.member = member
        self.container = container

    def extractor(self):
        return self.container.extractfile(self.member)

    @property
    def name(self):
        return self.member.name

    @property
    def size(self):
        return self.member.size


def get_archive_members(file_object, file_name):
    file_name = file_name.lower()
    if file_name.endswith('.zip'):
        zf = zipfile.ZipFile(file_object)
        for member in zf.infolist():
            yield _ZipMember(
                member,
                zf
            )

    elif file_name.endswith('.tar.gz') or file_name.endswith('.tgz'):
        tar = gzip.GzipFile(fileobj=file_object)
        zf = tarfile.TarFile(fileobj=tar)
        for member in zf.getmembers():
            if member.isfile():
                yield _TarMember(
                    member,
                    zf
                )

    elif file_name.endswith('.tar'):
        zf = tarfile.TarFile(fileobj=file_object)
        for member in zf.getmembers():
            # Sometimes when you make a tar file you get a
            # smaller index file copy that start with "./._".
            if member.isfile() and not member.name.startswith('./._'):
                yield _TarMember(
                    member,
                    zf
                )

    else:
        raise UnrecognizedArchiveFileExtension(os.path.splitext(file_name)[1])
