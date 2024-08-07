# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.apps import AppConfig

from tecken.base import symbolstorage


class BaseAppConfig(AppConfig):
    name = "tecken.base"

    def ready(self):
        symbolstorage.SYMBOL_STORAGE = symbolstorage.SymbolStorage.from_settings()
