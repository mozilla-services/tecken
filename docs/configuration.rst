=============
Configuration
=============

.. contents::

General Configuration
=====================

.. envvar:: DJANGO_CONFIGURATION

   Determines the settings class to use.

   Options:

   * ``Prod``: production configuration
   * ``Stage``: stage configuration
   * ``Localdev``: local development environment configuration

   The Dockerfile sets this to ``Prod``, but if you use docker-compose
   to start everything, it'll pick up ``Localdev``.

   .. code-block:: shell

      DJANGO_CONFIGURATION=Localdev


.. envvar:: DJANGO_SECRET_KEY

   You need to set a random ``DJANGO_SECRET_KEY``. It should be predictably
   random and a decent length.

   .. code-block:: shell

      DJANGO_SECRET_KEY=DontusethisinproductionbutitneedsbelongforCI1234567890


.. envvar:: ALLOWED_HOSTS

   The ``ALLOWED_HOSTS`` needs to be a list of valid domains that will be
   used to from the outside to reach the service. If there is only one
   single domain, it doesn't need to list any others. For example:

   .. code-block:: shell

       DJANGO_ALLOWED_HOSTS=symbols.mozilla.org

.. envvar:: SENTRY_DSN, SENTRY_PUBLIC_DSN

   This sets the Sentry DSN for the Python code and the JS code.

   For example:

   .. code-block:: shell

      SENTRY_DSN=https://bb4e266xxx:d1c1eyyy@sentry.prod.mozaws.net/001
      SENTRY_PUBLIC_DSN=https://bb4e266xxx@sentry.prod.mozaws.net/001


Gunicorn
========

You can set two environment variables:

.. envvar:: GUNICORN_TIMEOUT

    To specify the timeout value.

    https://docs.gunicorn.org/en/stable/settings.html#timeout

.. envvar:: GUNICORN_WORKERS

    To specify the number of gunicorn workers. The default is 4.

    You should set it to ``(2 x $num_cores) + 1``.

    https://docs.gunicorn.org/en/stable/settings.html#workers

    http://docs.gunicorn.org/en/stable/design.html#how-many-workers


AWS
===

The following variables need to be set for access:

.. envvar:: AWS_ACCESS_KEY_ID

   The AWS access key.

.. envvar:: AWS_SECRET_ACCESS_KEY

   The AWS Secret access key.

The account used needs to be able to read, write, and list the
``org.mozilla.crash-stats.symbols-public`` bucket which is in ``us-west-2``.

Tecken will never create S3 buckets--they are expected to exist.


Uploading, downloading, and symbolication
=========================================

.. envvar:: DJANGO_SYMBOL_URLS

   Comma-separated string of urls. Each url specifies an AWS S3 bucket.

   The form for the url is like this::

       # If symbols are in the root of the bucket
       https://s3-REGION.amazonaws.com/BUCKETNAME/

       # If symbols are in a directory in the bucket
       https://s3-REGION.amazonaws.com/BUCKETNAME/path/to/symbols/

   For publicly available buckets, add ``access=public`` to the querystring
   of the url.

   For example:

   .. code-block:: shell

      DJANGO_SYMBOL_URLS=https://s3-us-west-2.amazonaws.com/pubbucket/?access=public,https://s3-us-west-2.amazonaws.com/privatebucket/

   Tecken looks for symbols in the buckets in the order specified by
   ``DJANGO_SYMBOL_URLS``. This is used for downloading symbols and for
   symbolication.


.. envvar:: DJANGO_UPLOAD_DEFAULT_URL

   URL to indicates which bucket uploads go into by default.

   For example:

   .. code-block:: shell

      DJANGO_UPLOAD_DEFAULT_URL=https://s3-us-west-2.amazonaws.com/pubbucket/

.. envvar:: DJANGO_UPLOAD_URL_EXCEPTIONS

   Python dictionary that maps an email address or email address glob pattern
   to an upload URL.

   For example:

   .. code-block:: shell

      DJANGO_UPLOAD_BUCKET_EXCEPTIONS={"*example.com": "https://s3-us-west-2.amazonaws.com/privbucket/", "foo@bar.com": "https://s3-us-west-2.amazonaws.com/special/"}

.. envvar:: DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS

   Comma-delimited string specifying domains that we allow upload-by-download
   from.

   For example:

   .. code-block:: shell

      DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS=queue.taskcluster.net,public-artifacts.taskcluster.net

   .. Note::

      Note that, if you decide to add another domain, if requests to that domain
      trigger redirects to *another* domain you have to add that domain too.
      For example, if you have a ``mybigsymbolzips.example.com`` that redirects to
      ``cloudfront.amazonaws.net`` you need to add both.

Try builds
==========

Try build symbols are symbols that come from builds with a much more relaxed
access policy. That's why it's important that these kinds of symbols don't
override the non-Try build symbols. Also, the nature of them is much more
short-lived and when stored in S3 they should have a much shorter expiration
time than all other symbols.

.. envvar:: DJANGO_UPLOAD_TRY_SYMBOLS_URL

   URL to indicates which bucket Try symbol uploads go into by default.

   For example:

   .. code-block:: shell

      DJANGO_UPLOAD_TRY_SYMBOLS_URL=https://s3-us-west-2.amazonaws.com/pubbucket/try/


   If this isn't set, it defaults to the value of
   :envvar:`DJANGO_UPLOAD_DEFAULT_URL` with ``try`` added just after the bucket
   name.

PostgreSQL
==========

.. envvar:: DATABASE_URL

   This configures the database to use. The connection needs to be able connect
   in SSL mode.

   For example:

   .. code-block:: shell

      DATABASE_URL="postgres://username:password@hostname/databasename"

Redis Cache
===========

.. envvar:: REDIS_URL

   The URL to configure the Redis client.

   For example:

   .. code-block:: shell

      REDIS_URL="redis://test.v8jvds.0001.usw1.cache.amazonaws.com:6379/0"

.. envvar:: DJANGO_REDIS_IGNORE_EXCEPTIONS

   The Redis cache is used for caching. Because of that, exceptions that
   are kicked up by ``django-redis`` are ignored. This alleviates the
   site from going down when AWS Elasticache is unresponsive.

   If you want to disable this and have all Redis Cache exceptions result in
   an HTTP 500 an an error sent to Sentry, set the variable to False.

   For example:

   .. code-block:: shell

      DJANGO_REDIS_IGNORE_EXCEPTIONS=False

   .. seealso::

      * https://github.com/jazzband/django-redis#memcached-exceptions-behavior
      * https://github.com/jazzband/django-redis#log-ignored-exceptions

.. envvar:: DJANGO_REDIS_SOCKET_CONNECT_TIMEOUT

   Defaults to 1 second.

.. envvar:: DJANGO_REDIS_SOCKET_TIMEOUT

   Defaults to 2 seconds.

Redis Store
===========

The Redis Store points to a second Redis instance used for caching the output
of parsing symbols files.

.. envvar:: REDIS_STORE_URL

   The URL to configure the Redis client for the Redis Store.

   For example:

   .. code-block:: shell

      REDIS_STORE_URL="redis://store.deef34.0001.usw1.cache.amazonaws.com:6379/0"

.. envvar:: DJANGO_REDIS_STORE_SOCKET_CONNECT_TIMEOUT

   Defaults to 1 second.

.. envvar:: DJANGO_REDIS_STORE_SOCKET_TIMEOUT

   Defaults to 2 seconds.

This cache is very large and needs to keep running even at max memory capacity.
It needs to be configured to have a ``maxmemory-policy`` config set to the
value ``allkeys-lru``.

In Docker (development) this is automatically set at start-up time but in
AWS ElastiCache `config is not a valid command`_. So this needs to be
configured once in AWS by setting up an `ElastiCache Redis Parameter Group`_.
In particular the expected config is: ``maxmemory-policy=allkeys-lru``.

Expected version is 3.2 or higher.

.. _`config is not a valid command`: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ClientConfig.RestrictedCommands.html
.. _`ElastiCache Redis Parameter Group`: http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/ParameterGroups.Redis.html#ParameterGroups.Redis.3-2-4

StatsD and metrics
==================

.. envvar:: DJANGO_STATSD_HOST

   Defaults to ``"localhost"``.

.. envvar:: DJANGO_STATSD_PORT

   Defaults to ``8125``.

.. envvar:: DJANGO_STATSD_NAMESPACE

   Defaults to ``""`` (empty string).


.. _auth-configuration:

Authentication
==============

Prod and stage
--------------

In the production and stage environments, Tecken uses Mozilla SSO which is a
self-hosted Auth0 instance that integrates with Mozilla's LDAP system.

.. envvar:: DJANGO_OIDC_RP_CLIENT_ID

.. envvar:: DJANGO_OIDC_RP_CLIENT_SECRET

.. envvar:: DJANGO_OIDC_OP_AUTHORIZATION_ENDPOINT

.. envvar:: DJANGO_OIDC_OP_TOKEN_ENDPOINT

.. envvar:: DJANGO_OIDC_OP_USER_ENDPOINT

.. envvar:: DJANGO_OIDC_VERIFY_SSL

.. envvar:: DJANGO_ENABLE_AUTH0_BLOCKED_CHECK

.. seealso::

   https://mozilla-django-oidc.readthedocs.io/en/stable/settings.html


Local development
-----------------

For local development, we use this configuration:

.. code-block:: shell

    DJANGO_OIDC_RP_CLIENT_ID=1
    DJANGO_OIDC_RP_CLIENT_SECRET=bd01adf93cfb
    DJANGO_OIDC_OP_AUTHORIZATION_ENDPOINT=http://oidc.127.0.0.1.nip.io:8081/openid/authorize
    DJANGO_OIDC_OP_TOKEN_ENDPOINT=http://oidcprovider:8080/openid/token
    DJANGO_OIDC_OP_USER_ENDPOINT=http://oidcprovider:8080/openid/userinfo
    DJANGO_OIDC_VERIFY_SSL=False
    DJANGO_ENABLE_AUTH0_BLOCKED_CHECK=False

To use the provider:

1. Load http://localhost:3000
2. Click "Sign In" to start an OpenID Connect session on ``oidcprovider``
3. Click "Sign up" to create an ``oidcprovider`` account:
    * Username: A non-email username, like ``username``
    * Email: Your email address
    * Password: Any password, like ``password``
4. Click "Authorize" to authorize Tecken to use your ``oidcprovider`` account
5. You are returned to http://localhost:3000. If needed, a parallel Tecken User
   will be created, with default permissions and identified by email address.

You'll remain logged in to ``oidcprovider``, and the account will persist until
the ``oidcprovider`` container is stopped.
You can visit http://oidc.127.0.0.1.nip.io:8081/account/logout to manually log
out.
