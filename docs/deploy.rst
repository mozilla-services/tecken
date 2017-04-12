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

Redis cache
===========

The environment variable that needs to be set is: ``REDIS_URL``
and it can look like this::

    redis://hostname:6379/0

The cache
