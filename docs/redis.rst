===================
Redis Documentation
===================

Usage
=====

Tecken uses Redis for miscellaneous caching and as a broker for message queue
workers (TO BE UPDATED).


Usage In Django
===============

Within the Django code, these two are accessible in this way:

.. code-block:: python

    from django.core.cache import caches

    regular_cache = caches['default']

The first ("default") cache is also available in this form:

.. code-block:: python

    from django.core.cache import cache

    regular_cache = cache

Because it uses the `django-redis`_ and the Django Cache framework API you can
use it for all other sorts of caching such as caching sessions or cache control
for HTTP responses. Another feature of this is that you can bypass the default
expiration by explicitly setting a ``None`` timeout which means it's
persistent. For example:

.. code-block:: python

    from django.core.cache import cache

    cache.set('key', 'value', timeout=None)


.. _`django-redis`: https://niwinz.github.io/django-redis/latest/

CLIs
====

To go into CLI of the Redis database use this shortcuts:

.. code-block:: shell

    $ make redis-cache-cli

From there you can see exactly what's stored. For example, to see the list
of all symbols stored in the LRU cache:

.. code-block:: shell

    $ make redis-cache-cli

    redis-cache:6379> keys *
    1) ":1:d0f08e5ed1882049b74f1962103df580"
    2) ":1:02b212452eb0d18d6493d1f6a9de46ea"
    3) ":1:408a56890ff831bbd5ee91e73ddd5df8"
    4) ":1:9b46fc5d122c3e02b89a301a9e62b69a"
    5) ":1:e955c1adcc9d733bb77f9bb54d583a2c"
    6) ":1:django.contrib.sessions.cached_dbqkysb6y4gcbgpqkgnebd6yfjvmwzi5ks"
    7) ":1:django.contrib.sessions.cached_dbrwjkw2ef9xa5mszl2c3me2eh6yuvylum"
