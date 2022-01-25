# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.core import checks
from django.conf import settings
from tecken.storage import StorageBucket, StorageError


def check_storage_urls(app_configs, **kwargs):
    errors = []
    checked = []

    def check_url(url, setting_key):
        if url in checked:
            return
        bucket = StorageBucket(url)
        if not bucket.private:
            return
        try:
            if not bucket.exists():
                errors.append(
                    checks.Error(
                        f"Unable to connect to {url} (bucket={bucket.name!r}), "
                        f"because bucket not found",
                        id="tecken.health.E001",
                    )
                )
        except StorageError as error:
            errors.append(
                checks.Error(
                    f"Unable to connect to {url} (bucket={bucket.name!r}), "
                    f"due to {error.backend_msg}",
                    id="tecken.health.E002",
                )
            )
        else:
            checked.append(url)

    for url in settings.SYMBOL_URLS:
        check_url(url, "SYMBOL_URLS")
    for url in settings.UPLOAD_URL_EXCEPTIONS.values():
        check_url(url, "UPLOAD_URL_EXCEPTIONS")

    return errors
