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

    # If development server
    DJANGO_CONFIGURATION=Dev

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

**Note!** There are two configurations, related to S3, that needs to be
configured (presumably different) on every deployment environment.
They are: ``DJANGO_SYMBOL_URLS`` and ``DJANGO_UPLOAD_DEFAULT_URL``.
See the section below about **AWS S3**.

Google Cloud Platform
=====================

The only configuration varible you need to set is
``GOOGLE_APPLICATION_CREDENTIALS`` and its value need to be the path to a
``.json`` file that contains the (generated) Google Cloud Platform
credential details. For example:

.. code-block:: shell

    GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-service-account.json

Watch out for the fact that this file needs to be available within the
Docker container that runs the Python code.

.. note:: This is one of those few environment variables that is *not*
          prefixed with the string ``DJANGO_``.

AWS
===

Parts of Tecken does use ``boto3`` to talk directly to S3. For that
to work the following environment variables needs to be set:

.. code-block:: shell

    AWS_ACCESS_KEY_ID=AKI....H6A
    AWS_SECRET_ACCESS_KEY=....

This S3 access needs to be able to talk to the
``org.mozilla.crash-stats.symbols-public`` bucket which is in ``us-west-2``.

.. note:: This default is likely to change in mid-2017.

Gunicorn
========

At the moment, the only configuration for ``Gunicorn`` is that you can
set the number of workers. The default is 4 and it can be overwritten by
setting the environment variable ``GUNICORN_WORKERS``.

The number should ideally be a function of the web head's number of cores
according to this formula: ``(2 x $num_cores) + 1`` as `documented here`_.

.. _`documented here`: http://docs.gunicorn.org/en/stable/design.html#how-many-workers

AWS S3
======

First of all, Tecken will never *create* S3 buckets for you. They are
expected to already exist. There is one exception to this; if you do
local development with Docker and ``minio``, those configured buckets
are automatically created when the server starts. This is a convenience
just for local development to avoid needing any complicated instructions
to get up and running.

S3 buckets needs to be specified in two distinct places. One for where
Tecken can **read** symbols from and one for where Tecken can **write**.

Downloading
-----------

The *reading configuration* (used for downloading) is
called ``DJANGO_SYMBOL_URLS``. It's a
comma separated string. Each value, comma separated, is expected to be
a URL. The URL is deconstructed to extract out things like AWS region,
bucket name, prefix and whether the bucket should be reached by HTTP
(i.e. public) or by ``boto3`` (i.e. private).

What determines if a symbol URL is private or public is if it has
``access=public`` inside the query string.

The bucket name is always expected to the be first part of the URL path.
For example, in ``http://example.com/bucket-name-here/rest/is/prefix``
the bucket name is ``bucket-name-here`` and the prefix ``rest/is/prefix``.

Uploading
---------

The *write configuration* (used for uploading) is called potentially
by two different environment variables:

1. ``DJANGO_UPLOAD_DEFAULT_URL`` - a URL to indicate the
bucket where, by default, all uploads goes into unless it matches
an exception based on the uploader's email address.

2. ``DJANGO_UPLOAD_URL_EXCEPTIONS`` - a Python dictionary that maps an email
address or a email address glob pattern to a different URL.

As an example, imagine::

    DJANGO_UPLOAD_DEFAULT_URL=https://s3-us-west-2.amazonaws.com/mozilla-symbols-public/myprefix
    DJANGO_UPLOAD_BUCKET_EXCEPTIONS={'*example.com': 'https://s3-us-west-2.amazonaws.com/mozilla-symbols-private/', 'foo@bar.com': 'https://s3-us-west-2.amazonaws.com/mozilla-symbols-special'}

In this case, if someone, who does the upload, has email ``me@example.com``
all files within the uploaded ``.zip`` gets uploaded to a bucket called
``mozilla-symbols-private``.

.. note:: This functionality with ``DJANGO_UPLOAD_BUCKET_EXCEPTIONS`` is a bit
          clunky to say the least. It exists to get parity with symbol upload
          when it was done in Socorro. In the future, this kind of
          configuration is best moved to user land. That way superusers can
          decided about these kinds of exceptions.

Upload By Download
------------------

To upload symbols, clients can either HTTP POST a .zip file, or the client
can HTTP POST a form field called ``url``. Tecken will then download the
file from there and proceed as normal (as if the same file had been
part of the upload).

The environment variable to control this is
``DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS``. It's default is::

    queue.taskcluster.net, public-artifacts.taskcluster.net

Note that, if you decide to add another domain, if requests to that domain
trigger redirects to *another* domain you have to add that domain too.
For example, if you have a ``mybigsymbolzips.example.com`` that redirects to
``cloudfront.amazonaws.net`` you need to add both.

Symbolication
-------------

Symbolication uses the same configuration as Download does, namely
``DJANGO_SYMBOL_URLS``.

The value of the ``DJANGO_SYMBOL_URLS`` is encoded (as a short hash) into
every key Redis uses to store previous downloads as structured data.
Meaning, if you change ``DJANGO_SYMBOL_URLS`` on an already running,
all existing Redis store caching will be reset. And the old keys, that
are now no longer accessible, will slowly be recycled as the Redis store
uses a LRU eviction policy.

Try Builds
----------

Try build symbols are symbols that come from builds with a much more
relaxed access policy. That's why it's important that these kinds of
symbols don't override the non-Try build symbols. Also, the nature of
them is much more short-lived and when stored in S3 they should have
a much shorter expiration time than all other symbols.

The configuration key to set is ``DJANGO_UPLOAD_TRY_SYMBOLS_URL``
and it works very similar to ``DJANGO_UPLOAD_DEFAULT_URL``.

It's blank (aka. unset) by default, and if not explicitly set
it becomes the same as ``DJANGO_UPLOAD_DEFAULT_URL`` but with the prefix
``try`` after the bucket name and before anything else.

So if ``DJANGO_UPLOAD_TRY_SYMBOLS_URL`` isn't set and
``DJANGO_UPLOAD_DEFAULT_URL`` is ``http://s3.example.com/bucket/version0``
then ``DJANGO_UPLOAD_TRY_SYMBOLS_URL`` "becomes"
``http://s3.example.com/bucket/try/version0``.

If the URL points to a S3 bucket that doesn't already exist, you have to
manually create the S3 bucket first.

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

Redis Cache
===========

The environment variable that needs to be set is: ``REDIS_URL``
and it can look like this:

.. code-block:: shell

    REDIS_URL="redis://test.v8jvds.0001.usw1.cache.amazonaws.com:6379/0"

The amount of space needed is minimal. No backups are necessary.

In future versions of Tecken this Redis will most likely be used
as a broker for message queues by Celery.

Expected version is **3.2** or higher.

Redis Cache Errors
==================

By default, all exceptions that might happen when ``django-redis`` uses the
default Redis cache are swallowed. This is done to alleviate potential
disruption when AWS Elasticache is unresponsive, such as when it's upgraded.
The Redis Cache is supposed to be for the sake of optimization in that it
makes some slow computation unnecessary if repeated. But if the cache is
not working at all (operational errors for example) it's better that the
service continue to work even if it's slower than normal.

If you want to disable this and have all Redis Cache exceptions bubbled up,
which ultimately yields a 500 server error, change the environment variable to:

.. code-block:: shell

    DJANGO_REDIS_IGNORE_EXCEPTIONS=False

.. Note::

    If exceptions *do* happen, they are swallowed and logged and not entirely
    disregarded.

Redis Store
===========

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


Redis Socket Timeouts
=====================

There are two Redis connections. The "Redis Cache" and the "Redis Store".
These have both have the same defaults for
``SOCKET_CONNECT_TIMEOUT`` (1 second) and ``SOCKET_TIMEOUT`` (2 seconds).

The environment variables and their defaults are listed below:

.. code-block:: shell

    DJANGO_REDIS_SOCKET_CONNECT_TIMEOUT=1
    DJANGO_REDIS_SOCKET_TIMEOUT=2
    DJANGO_REDIS_STORE_SOCKET_CONNECT_TIMEOUT=1
    DJANGO_REDIS_STORE_SOCKET_TIMEOUT=2

StatsD
======

The three environment variables to control the statsd are as follows
(with their defaults):

1. ``DJANGO_STATSD_HOST`` (*localhost*)

2. ``DJANGO_STATSD_PORT`` (*8125*)

3. ``DJANGO_STATSD_NAMESPACE`` (*''* (empty string))


.. _auth0-configuration:

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


First Superuser
===============

Users need to create their own API tokens but before they can do that they
need to be promoted to have that permission at all. The only person/people
who can give other users permissions is the superuser. To bootstrap
the user administration you need to create at least one superuser.
That superuser can promote other users to superusers too.

This action does NOT require that the user signs in at least once. If the
user does not exist, it gets created.

The easiest way to create your first superuser is to use ``docker-compose``:

.. code-block:: shell

    docker-compose run web superuser peterbe@example.com


Microsoft Symbol Download
=========================

We have, in the Symbol Download, a feature that can attempt to download
missing symbols from Microsoft's server "on-the-fly". This is a new and
quite untested feature so it's disabled by default. To enable it set
the following environment variable:

.. code-block:: shell

    DJANGO_ENABLE_DOWNLOAD_FROM_MICROSOFT=True
