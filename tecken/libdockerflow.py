# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from pathlib import Path

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

    return errors


def get_version_info(basedir):
    """Returns version.json data from deploys"""
    path = Path(basedir) / "version.json"
    if not path.exists():
        return {}

    try:
        data = path.read_text()
        return json.loads(data)
    except (OSError, json.JSONDecodeError):
        return {}


def get_release_name(basedir):
    """Return a friendly name for the release that is running

    This pulls version data and then returns the best version-y thing available: the
    version, the commit, or "unknown" if there's no version data.

    :returns: string

    """
    version_info = get_version_info(basedir)
    version = version_info.get("version", "none")
    commit = version_info.get("commit")
    commit = commit[:8] if commit else "unknown"
    return f"{version}:{commit}"
