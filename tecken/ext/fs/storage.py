# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

from tecken.libstorage import StorageBackendBase, StorageError


class FSStorage(StorageBackendBase):
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def create(self):
        os.makedirs(self.path, exists_ok=True)

    def exists(self):
        try:
            return os.path.exists(self.path)
        except Exception as exc:
            raise StorageError(
                backend="fs", url=self.path, error="Unknown exception"
            ) from exc
