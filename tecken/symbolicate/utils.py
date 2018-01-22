# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.core.cache import caches


def make_symbol_key_cache_key(symbol_key):
    """return a string that is appropriate to send to django_redis that
    represent a "symbol key".
    A symbol key is expected to be a tuple of two strings like this:

        ('xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2')

    ...for example.
    """
    assert isinstance(symbol_key, (tuple, list)), symbol_key
    assert len(symbol_key) == 2, symbol_key
    return 'symbol:{}/{}'.format(*symbol_key)


def invalidate_symbolicate_cache(symbol_keys):
    all_keys = []
    for symbol_key in symbol_keys:
        # Every symbol, for the sake of symbolication, is stored in two
        # ways:
        # 1) symbol_key + ':keys'  (plain SET)
        # 2) symbol_key (as hashmap)
        cache_key = make_symbol_key_cache_key(symbol_key)
        all_keys.append(cache_key)  # the hashmap
        all_keys.append(cache_key + ':keys')  # the list of all offsets

    store = caches['store']
    store.delete_many(all_keys)
