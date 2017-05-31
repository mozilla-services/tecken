=============
Configuration
=============

.. contents::

High-level things
=================

Tecken requires the following services in production:

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

    DJANGO_SENTRY_DSN=https://bb4e266xxx:d1c1eyyy@sentry.prod.mozaws.net/001
    DJANGO_SENTRY_PUBLIC_DSN=https://bb4e266xxx@sentry.prod.mozaws.net/001

AWS
===

Parts of Tecken does use ``boto3`` to talk directly to S3. For that
to work the following environment variables needs to be set:

.. code-block:: shell

    AWS_ACCESS_KEY_ID=AKI....H6A
    AWS_SECRET_ACCESS_KEY=....

This S3 access needs to be able to talk to the
``org.mozilla.crash-stats.symbols-public`` bucket which is in ``us-west-2``.

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

In future versions of Tecken this Redis will most likely be used
as a broker for message queues by Celery.

Expected version is **3.2** or higher.

Redis LRU
=========

Aka. Redis Store. This is the cache used for downloaded symbol files.
The environment value key is called ``REDIS_STORE_URL`` and it can
look like this:

.. code-block:: shell

    REDIS_STORE_URL="redis://store.deef34.0001.usw1.cache.amazonaws.com:6379/0"


This Redis will steadily grow large so it needs to not fail when it reaches
max memory capacity. For this to work, it needs to be configured to have a
``maxmemory-policy`` config set to the value ``allkeys-lru``.

In Docker (development) this is automatically set at start-up time but in
AWS ElastiCache `config is not a valid command`_. So this needs to
configured once in AWS by setting up an `ElastiCache Redis Parameter Group`_.
In particular the expected config is: ``maxmemory-policy=allkeys-lru``.

Expected version is **3.2** or higher.

.. _`config is not a valid command`: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ClientConfig.RestrictedCommands.html
.. _`ElastiCache Redis Parameter Group`: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ParameterGroups.Redis.html#ParameterGroups.Redis.3-2-4

StatsD
======

The three environment variables to control the statsd are as follows
(with their defaults):

1. ``DJANGO_STATSD_HOST`` (*localhost*)

2. ``DJANGO_STATSD_PORT`` (*8125*)

3. ``DJANGO_STATSD_NAMESPACE`` (*''* (empty string))


Auth0
=====

For authentication to work, you need to have an Auth0 account and its
credentials. You also need a domain so you can figure out certain
URLs. You need the client ID and the client secret. Put these into
the environment variables like this:

.. code-block:: shell

    DJANGO_OIDC_RP_CLIENT_ID=clientidhereclientidhere
    DJANGO_OIDC_RP_CLIENT_SECRET=clientsecrethereclientsecrethere

The default domain is ``auth.mozilla.auth0.com``. That has consequently
been used to set up the following defaults:

.. code-block:: shell

    DJANGO_OIDC_OP_AUTHORIZATION_ENDPOINT=https://auth.mozilla.auth0.com/authorize
    DJANGO_OIDC_OP_TOKEN_ENDPOINT=https://auth.mozilla.auth0.com/oauth/token
    DJANGO_OIDC_OP_USER_ENDPOINT=https://auth.mozilla.auth0.com/userinfo

If your domain is different, override these above three environment
variables with your domain.

Note! Tecken uses `Auth0`_ which follows the OpenID Connect protocol.
The configuration actually requires the above mentioned URLs and when
you use Auth0, the URLs are quite constant. But if you use another OpenID
Connect provider, use the domain (e.g. ``myoidc.example.com``) and go to
``https://myoidc.example.com/.well-known/openid-configuration`` and from
there it should publish the authorization, token and user endpoints.

.. _`Auth0`: https://auth0.com/
