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


PostgreSQL
==========

The environment variable that needs to be set is: ``DATABASE_URL``
and it can look like this::

    postgres://username:password@hostname/databasename

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
and it can look like this::

    redis://test.v8jvds.0001.usw1.cache.amazonaws.com:6379/0

The amount of space needed is minimal. No backups are necessary.

In future versions of ``tecken`` this Redis will most likely be used
as a broker for message queues inside Celery.


Redis LRU
=========

Aka. Redis Store. This is the cache used for downloaded symbol files.
It will quickly grow large so it needs to not fail when it reaches max
memory. This is done by once settings the ``maxmemory-policy`` Redis
configuration key.

When using Redis in AWS ElastiCache you don't need to specify a ``maxmemory``
amount since it's automatically implied by the site of the instance it's
deployed on.

The setting that needs to be done can be done once from the Redis CLI

.. Note::

  See documentation_ says: *The ``maxmemory`` parameter cannot be modified.*

.. _documentation: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ParameterGroups.Redis.html#ParameterGroups.Redis.NodeSpecific
