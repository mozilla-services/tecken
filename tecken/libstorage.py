# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


class StorageError(Exception):
    """A backend-specific client reported an error."""

    # FIXME(willkg): this is unhelpful and drops a lot of exception magic
    def __init__(self, backend, url, error):
        self.backend = backend
        self.url = url
        self.backend_msg = f"{type(error).__name__}: {error}"

    def __str__(self):
        return f"{self.backend} backend ({self.url}) raised {self.backend_msg}"
