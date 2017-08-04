# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re

from django.core.cache.backends.locmem import LocMemCache


class RedisLocMemCache(LocMemCache):
    """Expanding Django's LocMemCache with the methods that are expected
    beyond the default cache but as if it was backed by Redis"""

    def iter_keys(self, search_term):
        regex = re.compile(search_term.replace('*', '.'))
        for key in self._cache:
            if regex.findall(key):
                # the "raw key" will always be "<PREFIX>:<VERSION>:<KEY>"
                yield key.split(':', 2)[2]
