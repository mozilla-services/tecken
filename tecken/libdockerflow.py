# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import logging
from pathlib import Path

from django.core import checks

from tecken.base.symbolstorage import symbol_storage
from tecken.libstorage import StorageError


logger = logging.getLogger("tecken")


def check_storage_urls(app_configs, **kwargs):
    errors = []
    for backend in symbol_storage().get_download_backends(False):
        try:
            if not backend.exists():
                errors.append(
                    checks.Error(
                        f"Unable to connect to {backend!r}), because bucket not found",
                        id="tecken.health.E001",
                    )
                )
        except StorageError as error:
            logger.exception("Error when testing whether storage backend exists")
            errors.append(
                checks.Error(
                    f"Connection error: {error}",
                    id="tecken.health.E002",
                )
            )
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
