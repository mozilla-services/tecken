===================
Redis Documentation
===================

Usage
=====

Redis is used for two distinct purposes and the different
configurations shouldn't be mixed.

One is used as an LRU cache for the Symbolication service. It's basically
an alternative to a disk cache where eviction is automatically taken care
of. The LRU functionality is dependent on two things:

* A ``maxmemory`` configuration being something other than 0 otherwise it
  will just continue to fill up until the server/computer runs out of RAM.

* A ``maxmemory-policy`` setting being someting other than ``noeviction``.

The other Redis server is used for miscellaneous caching and as a broker
for message queue workers (TO BE UPDATED).

Predicted Production Use
========================

In 2014, `Ted calculated`_ that we need approximately 35GB storage to
have a 99% cache hit ratio of all symbols that Socorro needs when
symbolicating.
In Tecken we don't store downloaded symbol files, but instead we store
a minor subset of the downloaded files so `by estimates`_ we only store 20%
of that weight. In conclusion, to maintain a 99% cache hit ratio we need
6GB and 2GB for a 95% cache hit ratio.

.. _`Ted calculated`: https://bugzilla.mozilla.org/show_bug.cgi?id=981079#c1
.. _`by estimates`: https://bugzilla.mozilla.org/show_bug.cgi?id=981079#c9

Usage In Django
===============

Within the Django code, these two are accessible in this way:

.. code-block:: python

    from django.core.cache import caches

    regular_cache = caches['default']
    lru_cache = caches['store']

The first ("default") cache is also available in this form:

.. code-block:: python

    from django.core.cache import cache

    regular_cache = cache

Because it uses the `django-redis`_ and the Django Cache framework API
you can use it for all other sorts of caching such as caching sessions or
cache control for HTTP responses. Another feature of this is that you can
bypass the default expiration by explicitly setting a ``None`` timeout
which means it's persistent. For example:

.. code-block:: python

    from django.core.cache import cache

    cache.set('key', 'value', timeout=None)


.. _`django-redis`: https://niwinz.github.io/django-redis/latest/

CLIs
====

To go into CLI of each two Redis database use these shortcuts:

.. code-block:: shell

    $ make redis-cache-cli
    (...or...)
    $ make redis-store-cli

From there you can see exactly what's stored. For example, to see the list
of all symbols stored in the LRU cache:

.. code-block:: shell

    $ make redis-store-cli

    redis-store:6379> keys *
    1) ":1:symbol:xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2"
    2) ":1:symbol:wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2"

Configuration
=============

The default configuration, in Docker, for the Redis service used as a LRU
cache is defined in the ``docker/images/redis/redis.conf`` file and it
sets a ``maxmemory`` number that is appropriate for local development.
When deployed in production this should be better tuned to fit the server
it's on. This configuration also sets the right ``maxmemory-policy`` to
the value ``allkeys-lru`` which is also ideal for production usage.

To see the configuration, use the ``redis-store`` service in the shell:

.. code-block:: shell

    $ make redis-store-cli

    redis-store:6379> config get maxmemory
    1) "maxmemory"
    2) "524288000"
    redis-store:6379> config get maxmemory-policy
    1) "maxmemory-policy"
    2) "allkeys-lru"

To override this, simply use ``config set`` instead of ``config get``.
For example:

.. code-block:: shell

    $ make redis-store-cli

    redis-store:6379> config set maxmemory 100mb
    OK
    redis-store:6379> config get maxmemory
    1) "maxmemory"
    2) "104857600"

To get an insight into the state of the Redis service use the ``INFO`` command:

.. code-block:: shell

    $ make redis-store-cli

    redis-store:6379> info
    # Server
    redis_version:3.2.8
    redis_git_sha1:00000000
    redis_git_dirty:0
    redis_build_id:9c531c9c1d171a62
    redis_mode:standalone
    os:Linux 4.9.13-moby x86_64
    arch_bits:64
    multiplexing_api:epoll
    <redacted>


If you stop the Docker service and start it again it will revert to the
configuration in ``docker/images/redis/redis.conf``.

Unit Testing in Docker
======================

Since Redis is the actual cache backend used even in unit tests, its
data is persistent between tests. To avoid confusion between unit tests
use the ``clear_redis_store`` pytest fixture. For example:

.. code-block:: python

    from django.core.cache import cache

    def test_storage1(clear_redis_store):
        assert not cache.get('foo')
        cache.set('foo', 'bar')

    def test_storage2(clear_redis_store):
        assert not cache.get('foo')
        cache.set('foo', 'different')
