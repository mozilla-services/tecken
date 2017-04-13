===================================
Putting Symbol Server in production
===================================

.. contents::

High-level things
=================

``tecken`` requires the following services in production:

1. PostgreSQL 9.5

2. Redis for general "performance" caching

3. Redis for LRU caching


General Configuration
=====================

The Django settings depends on there being an environment variable
called ``DJANGO_CONFIGURATION``. The ``Dockerfile`` automatically sets
this to ``Prod`` and the ``Dockerfile.dev`` overrides it to ``Dev``.

.. code-block:: shell

    # If production
    DJANGO_CONFIGURATION=Prod

    # If stage
    DJANGO_CONFIGURATION=Stage

You need to set a random ``DJANGO_SECRET_KEY``. It should be predictably
random and a decent length:

.. code-block:: shell

    DJANGO_SECRET_KEY=sSJ19WAj06QtvwunmZKh8yEzDdTxC2IPUXfea5FkrVGNoM4iOp

The ``ALLOWED_HOSTS`` needs to be a list of valid domains that will be
used to from the outside to reach the service. If there is only one
single domain, it doesn't need to list any others. For example:

.. code-block:: shell

    DJANGO_ALLOWED_HOSTS=symbols.mozilla.org

For Sentry the key is ``SENTRY_DSN`` which is sensitive but for the
front-end (which hasn't been built yet at the time of writing) we also
need the public key called ``SENTRY_PUBLIC_DSN``. For example:

.. code-block:: shell

    SENTRY_DSN=https://bb4e266xxx:d1c1eyyy@sentry.prod.mozaws.net/001
    SENTRY_PUBLIC_DSN=https://bb4e266xxx@sentry.prod.mozaws.net/001


PostgreSQL
==========

The environment variable that needs to be set is: ``DATABASE_URL``
and it can look like this:

.. code-block:: shell

    DATABASE_URL="postgres://username:password@hostname/databasename"

The connection needs to be able connect in SSL mode.
The database server is expected to have a very small footprint. So, as
long as it can scale up in the future it doesn't need to be big.

.. Note::

    Authors note; I don't actually know the best practice for
    setting the credentials or if that's automatically "implied"
    the VPC groups.

Redis cache
===========

The environment variable that needs to be set is: ``REDIS_URL``
and it can look like this:

.. code-block:: shell

    REDIS_URL="redis://test.v8jvds.0001.usw1.cache.amazonaws.com:6379/0"

The amount of space needed is minimal. No backups are necessary.

In future versions of ``tecken`` this Redis will most likely be used
as a broker for message queues inside Celery.


Redis LRU
=========

Aka. Redis Store. This is the cache used for downloaded symbol files.
It will quickly grow large so it needs to not fail when it reaches max
memory. This is done by once settings the ``maxmemory-policy`` Redis
configuration key. First of all, the environment variable
that needs to be set is ``REDIS_STORE_URL``, like this:

.. code-block:: shell

    REDIS_STORE_URL="redis://store.deef34.0001.usw1.cache.amazonaws.com:6379/0"

When using Redis in AWS ElastiCache you don't need to specify a ``maxmemory``
amount since it's automatically implied by the site of the instance it's
deployed on.

The setting that needs to be set once from the Redis CLI with:

.. code-block:: shell

    > config set maxmemory-policy allkeys-lru
    OK

.. Note::

  See documentation_ says: *The maxmemory parameter cannot be modified.*

.. _documentation: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ParameterGroups.Redis.html#ParameterGroups.Redis.NodeSpecific
