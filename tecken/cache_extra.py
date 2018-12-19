# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re

import msgpack
from django_redis.serializers.msgpack import MSGPackSerializer as _MSGPackSerializer

from django.core.cache.backends.locmem import LocMemCache


class MockClient:
    """This exists to satisfy the ability to use get_redis_connection()
    in dockerflow checks even though the backend is actually a glorified
    LocMemCache instance.
    """

    def __init__(self):
        pass

    def get_client(self, write=True):
        self.write = write
        return self

    def ping(self):
        return "pong"

    def info(self):
        raise NotImplementedError


class RedisLocMemCache(LocMemCache):
    """Expanding Django's LocMemCache with the methods that are expected
    beyond the default cache but as if it was backed by Redis"""

    def iter_keys(self, search_term):
        regex = re.compile(search_term.replace("*", "."))
        for key in self._cache:
            if regex.findall(key):
                # the "raw key" will always be "<PREFIX>:<VERSION>:<KEY>"
                yield key.split(":", 2)[2]

    @property
    def client(self):
        return MockClient()


class MSGPackSerializer(_MSGPackSerializer):
    """The only reason for this class is to be able to override the `loads` method
    in the original django_redis.serializers.msg.MSGPackSerializer class.

    In django_redis is uses `msgpack.loads(value, encoding='utf-8')` which is
    deprecated in msgpack 0.6.0.

    The reason django_redis can't easily make this change is that it would break
    things for people who use msgpack <=0.5.1.
    See https://github.com/niwinz/django-redis/issues/310
    """

    def loads(self, value):
        return msgpack.loads(value, raw=False)
