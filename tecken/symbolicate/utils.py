# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib

from django.core.cache import caches
from django.conf import settings


def make_symbol_key_cache_key_default_prefix():
    """Return a string that is an appropriate non-empty prefix for the
    symbol cache keys.

    This implementation is very specific so it's important that you
    only use this one function throughout or you might end up
    generating different prefixes from different angles and not notice.
    """
    symbol_urls = ''.join(settings.SYMBOL_URLS)
    hash_ = hashlib.md5(symbol_urls.encode('utf-8')).hexdigest()
    # Because this is going to be used in every key, it behoves use
    # to shorten it a little.
    return hash_[:5]


def make_symbol_key_cache_key(symbol_key, prefix=None):
    """return a string that is appropriate to send to django_redis that
    represent a "symbol key".
    A symbol key is expected to be a tuple of two strings like this:

        ('xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2')

    ...for example.
    """
    if prefix is None:
        prefix = make_symbol_key_cache_key_default_prefix()
    assert prefix, prefix
    assert isinstance(symbol_key, (tuple, list)), symbol_key
    assert len(symbol_key) == 2, symbol_key
    return 'symbol:{}:{}/{}'.format(prefix, *symbol_key)


def invalidate_symbolicate_cache(symbol_keys, prefix=None):
    """Makes sure all symbolication caching stored for this list of
    symbol keys is removed from the Redis store."""
    all_keys = []
    for symbol_key in symbol_keys:
        # Every symbol, for the sake of symbolication, is stored in two
        # ways:
        # 1) symbol_key + ':keys'  (plain SET)
        # 2) symbol_key (as hashmap)
        cache_key = make_symbol_key_cache_key(symbol_key, prefix=prefix)
        all_keys.append(cache_key)  # the hashmap
        all_keys.append(cache_key + ':keys')  # the list of all offsets

    store = caches['store']
    store.delete_many(all_keys)
