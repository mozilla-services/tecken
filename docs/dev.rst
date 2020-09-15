=============================
Admin/Developer Documentation
=============================

.. contents::
   :local:


Setting up a development environment
====================================

You can set up a development environment with:

.. code-block:: shell

   # Builds Docker containers
   $ make build

   # Initializes service state (db)
   $ make setup


Tecken has a webapp.

To run the webapp, do:

.. code-block:: shell

   # Runs web and ui and required services
   $ make run


Now a development server should be available at
``http://localhost:3000``.

To test the symbolication run::

   $ curl --user-agent "example/1.0" -d '{"stacks":[[[0,11723767],[1, 65802]]],"memoryMap":[["xul.pdb","44E4EC8C2F41492B9369D6B9A059577C2"],["wntdll.pdb","D74F79EB1F8D4A45ABCD2F476CCABACC2"]],"version":4}' http://localhost:3000/symbolicate/v5


Database migrations
===================

We use Django's ORM and thus we do database migrations using Django's
migration system.

Do this::

   $ make shell
   app@xxx:/app$ ./manage.py makemigration --name "BUGID_desc" APP


Managing dependencies
=====================


Python dependencies
-------------------

Python dependencies for all parts of Socorro are split between two files:

1. ``requirements/default.txt``, containing dependencies that Socorro uses
   directly.
2. ``requirements/constraints.txt``, containing dependencies required by the
   dependencies in ``default.txt`` that Socorro does not use directly.

Dependencies in both files must be pinned and hashed. Use
`hashin <https://pypi.python.org/pypi/hashin>`_.

For example, to add ``foobar`` version 5::

  $ hashin -r requirements/default.txt foobar==5

If ``foobar`` has any dependencies that would also be installed, you must add
them to the constraints file::

  $ hashin -r requirements/constraints.txt bazzbiff==4.0

Then rebuild your docker environment::

  $ make build

If there are problems, it'll tell you.

.. Note::

   If you're unsure what dependencies to add to the constraints file, the error
   from running ``make build`` should include a list of dependencies that were
   missing, including their version numbers and hashes.


JavaScript dependencies
-----------------------

Tecken uses `yarn <https://yarnpkg.com/>`_ for JavaScript dependencies. Use the
``yarn`` installed in the Docker frontend container:

.. code-block:: shell

    $ docker-compose run frontend bash

    # display packages that can be upgraded
    node@xxx:/app$ yarn outdated

    # example of upgrading an existing package
    node@xxx:/app$ yarn upgrade date-fns --latest

    # example of adding a new package
    node@xxx:/app$ yarn add some-new-package

When you're done, you have to rebuild the frontend Docker container:

.. code-block:: shell

    $ docker-compose build frontend

Your change should result in changes to ``frontend/package.json`` *and*
``frontend/yarn.lock`` which needs to both be checked in and committed.


Testing
=======

Unit tests
----------

Tecken uses `pytest <https://pytest.org/>`_ for unit tests.

To run the tests, do:

.. code-block:: shell

   $ make test

Tests go in ``tests/``. Data required by tests goes in ``tests/data/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ make testshell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ pytest tests/test_symbolicate.py


System tests
------------

System tests are located in the repository in ``systemtests/``. See the
``README.rst`` there for usage.

System tests can be run against any running environment: local, stage, or prod.


Frontend JavaScript tests
-------------------------

There are no tests for the JavaScript code. For now, run the app and click
through the site:

1. go to website
2. wait for front page to load
3. click on "Home"
4. click on "Downloads missing"
5. click on "Symbolication"
6. click on "Help"
7. click on "Log in" and log in
8. click on "Home"
9. click on "Downloads missing"
10. click on "User management"
11. click on "API tokens"
12. click on "Uploads"
13. click on "Symbolication"
14. click on "Help"
15. click on "Sign out"


Accounts and first superuser
============================

Users need to create their own API tokens but before they can do that they
need to be promoted to have that permission at all. The only person/people
who can give other users permissions is the superuser. To bootstrap
the user administration you need to create at least one superuser.
That superuser can promote other users to superusers too.

This action does NOT require that the user signs in at least once. If the
user does not exist, it gets created.

The easiest way to create your first superuser is to use ``docker-compose``:

.. code-block:: shell

    docker-compose run --rm web superuser yourname@example.com

Additionally, in a local development environment, you can create a
corresponding user in the oidcprovider service like this:

.. code-block:: shell

   docker-compose exec oidcprovider /code/manage.py createuser yourname yourpassword yourname@example.com

Running ``gunicorn`` locally
============================

To run ``gunicorn`` locally, which has concurrency, run:

.. code-block:: shell

   $ make gunicorn

You might want to temporarily edit ``.env`` and set ``DJANGO_DEBUG=False``
to run it in a more production realistic way.


Prod-like running locally
=========================

First you need to start Tecken with a set of configurations that
mimics what's required in prod, except we're doing this in docker.

To do that, you need to set ``DJANGO_CONFIGURATION=Prodlike`` and
run the gunicorn workers:

.. code-block:: shell

    $ docker-compose run --service-ports --user 0  web bash

This will start 4 ``gunicorn`` workers exposed on ``0.0.0.0:8000`` and
exposed outside of docker onto your host.

.. note::

   If this fails to start, some exceptions might be hidden. If so, do::

      $ make shell
      app@xxx:/app$ export DJANGO_UPLOAD_DEFAULT_URL=http://minio:9000/testbucket
      app@xxx:/app$ export DJANGO_SYMBOL_URLS=http://minio:9000/testbucket
      app@xxx:/app$ export DJANGO_CONFIGURATION=Prodlike
      app@xxx:/app$ gunicorn tecken.wsgi:application -b 0.0.0.0:8000 --workers 4 --access-logfile -

That configuration **forces** you to run with ``DEBUG=False`` independent
of what value you have set in ``.env`` for ``DEBUG``. Thus making it easy
to switch from regular debug-mode development to prod-like serving.

The second step for this to be testable is to reach the server with ``HTTPS``
or else the app will forcibly redirect you to the ``https://`` equivalent of
whatever URL you attempt to use (e.g. ``http://localhost:8000/`` redirects
to ``https://localhost:8000/``)

To test this, run a local Nginx server. But first, create a suitable
hostname. For example, ``prod.tecken.dev``. Edit ``/etc/hosts`` and enter
a line like this::

    127.0.0.1       prod.tecken.dev

To generate an nginx config file, run ``./test-with-nginx/generate.py``.
That will be print out a Nginx configuration file you can put where
you normally put Nginx configuration files. For example:

.. code-block:: shell

    $ ./test-with-nginx/generate.py --help
    $ ./test-with-nginx/generate.py > /etc/nginx/sites-enabled/tecken.conf
    $ # however you reload nginx


Frontend and prod-like running locally
======================================

When Tecken is deployed with continuous integration, it builds the static
assets files for production use. These files are served by Django using
Whitenoise. Basically, anything that isn't a matched Django URL-to-view
gets served as a static file, if matched.

Suppose you want to run the prod-like frontend locally. For example, you
might be hunting a frontend bug that only happens when the assets are
minified and compiled. To do that you have to manually build the static assets:

.. code-block:: shell

    $ cd frontend
    $ yarn
    $ yarn run build

This should create ``frontend/build/*`` files. For example
``static/js/main.6d3b4de8.js``. This should now be available *thru* Django
at ``http://localhost:8000/static/js.main.6d3b4de8.js``.

When you're done you can delete ``frontend/build`` and
``frontend/node_modules``.


Running things in background vs foreground
==========================================

By default ``make run`` is wired to start three things in the foreground:

* Django (aka. ``web``)

* Celery (aka. ``worker``)

* React dev server (aka. ``frontend``)

This is done by running ``docker-compose up web worker frontend``. These
services' output is streamed together to stdout in the foreground that
this ``docker-compose up ...`` runs.

All other things that these depend on are run in the background. Meaning
you don't see, for example, what the ``minio`` service does. It knows to
*start* because in ``docker-compose.yml`` ``web`` is **linked** to
``minio``.

If you instead want to run, for example, ``minio`` in the foreground here's
how:

1. Comment out ``minio`` from the ``links`` part of ``web`` in ``docker-compose.yml``

2. In a terminal run ``docker-compose up minio``.

3. In another terminal run ``make run``

Alternatively, just do step 1, from the list above, and then run:
``docker-compose up minio web worker frontend``.


All metrics keys
================

To get insight into all metrics keys that are used, a special Markus backend
is enabled called ``tecken.markus_extra.LogAllMetricsKeys``. It's enabled
by default in local development. And to inspect its content you can either
open ``all-metrics-keys.json`` directly (it's git ignored) or you can run:

.. code-block:: shell

    $ make shell
    app@xxx:/app$ ./bin/list-all-metrics-keys.py

Now you can see a list of all keys that are used. Take this and, for example,
make sure you make a graph in Datadog of each and everyone. If there's a key
in there that you know you don't need or care about in Datadog, then delete
it from the code.

The file ``all-metrics-keys.json`` can be deleted any time and it will be
recreated again.


Celery in local development mode
================================

When you do something like ``make run`` it starts Django, the frontend
and the Celery worker. But it's important to note that it starts Celery
with ``--purge``. That means that every time you start up the worker,
all jobs that have been previously added to the Celery query are purged.

This is to prevent foot-shooting. Perhaps a rogue unit test that didn't mock
the broker and accidentally added hundreds of jobs that all fail.
Or perhaps you're working on a git branch that changes how the worker job
works and as you're jumping between git branches you start and stop the worker
so that the wrong jobs are sent using the wrong branch.

Another real thing that can happen is that when you're doing loadtesting of
the web app, and only run that in docker, but since the web app writes to
the same Redis (the broker) thousands of jobs might be written that never
get a chance to be consumed by the worker.

This is why ``docker-compose`` starts ``worker-purge`` instead of ``worker``
which is the same thing except it's started with ``--purge`` and this should
only ever be done on local docker development.


Minio (S3 mock server)
======================

When doing local development we, by default, mock AWS S3 and instead use
`minio`_. It's API compatible so it should reflect how AWS S3 works but
with the advantage that you don't need an Internet connection and real
S3 credentials just to test symbol uploads for example.

When started with docker, it starts a web server on ``:9000`` that you can
use to browse uploaded files. Go to ``http://localhost:9000``.

.. _`minio`: https://minio.io/


How to do local Upload by Download URL
======================================

When doing local development and you want to work on doing Symbol Upload
by HTTP posting the URL, you have a choice. Either put files somewhere
on a public network, or serve the locally.

Before we start doing local Upload By Download URL, you need to make your
instance less secure since you'll be using URLs like ``http://localhost:9090``.
Add ``DJANGO_ALLOW_UPLOAD_BY_ANY_DOMAIN=True`` to your ``.env`` file.

To serve them locally, first start the dev server (``make run``). Then
you need to start a bash shell in the current running web container:

.. code-block:: shell

    $ make shell

Now, you need some ``.zip`` files in the root of the project since it's
mounted and can be seen by the containers. Once they're there, start a
simple Python server:

.. code-block:: shell

    $ ls -lh *.zip
    $ python -m http.server --bind 0.0.0.0 9090

Now, you can send these in with ``tecken-loadtest`` like this:

.. code-block:: shell

    $ export AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxx
    $ python upload-symbol-zips.py http://localhost:8000 -t 160 --download-url=http://localhost:9090/symbols.zip

This way you'll have 3 terminals. 2 bash terminals inside the container
and one outside in the ``tecke-loadtests`` directory on your host.


Debugging auth
==============

There are many reasons for why authentication might not work. Most of the
pit falls lies with the the configuration and credentials around OpenID
Connect. I.e. Auth0 in our current case.

Another important thing is that on the Django side, caching and cookies work.

If you have trouble authenticating you can start the server and go to:
``http://localhost:8000/__auth_debug__``.  It will check that the cache
can work between requests and that session cookies can be set and read.


Debugging a "broken" Redis
==========================

By default, we have our Redis Cache configured to swallow all exceptions
(...and just log them). This is useful because the Redis Cache is only
supposed to make things faster. It shouldn't block things from working even
if that comes at a price of working slower.

To simulate that Redis is "struggling" you can use the
`CLIENT PAUSE <https://redis.io/commands/client-pause>`_ command. For example:

.. code-block:: shell

   $ make redis-cache-cli
   redis-cache:6379> client pause 30000
   OK

Now, for 30 seconds (30,000 milliseconds) all attempts to talk to Redis Cache
is going to cause a ``redis.exceptions.TimeoutError: Timeout reading from socket``
exception which gets swallowed and logged. But you *should* be able to use
the service fully.

For example, all things related to authentication, such as your session cookie
should continue to work because we use the ``cached_db`` backend in
``settings.SESSION_ENGINE``. It just means we have to rely on PostgreSQL to
verify the session cookie value on each and every request.


Giving users permission to upload
=================================

The user should write up a bug. See :ref:`upload-basics`.

If the user is a Mozilla employee, needinfo the user's manager and verify the
user needs upload permission.

If the user is not a Mozilla employee, find someone to vouch for the user.

Once vouched:

1. Log in to `<https://symbols.mozilla.org/users>`_
2. Use the search filter at the bottom of the page to find the user
3. Click to edit and make give them the "Uploaders" group (only).
4. Respond and say that they now have permission and should be able to either
   upload via the web or create an API Token with the "Upload Symbol Files"
   permission.
5. Resolve the bug.


Auth0 debugging
===============

Tecken uses Mozilla SSO. Anyone can log in, but by default accounts don't have
special permissions to anything.

A potential pattern is that a user logs in with their work email
(e.g. ``example@mozilla.com``), gets permissions to create API tokens,
the uses the API tokens in a script and later *leaves* the company whose
email she *used* she can no longer sign in to again. If this happens
her API token should cease to work, because it was created based on the
understanding that she was an employee and has access to the email address.

This is why there's a piece of middleware that periodically checks that
users who once authenticated with Auth0 still is there and **not blocked**.

Being "blocked" in Auth0 is what happens, "internally", if a user is removed
from LDAP/Workday and Auth0 is informed. There could be other reasons why
a user is blocked in Auth0. Whatever the reasons, users who are blocked
immediately become inactive and logged out if they're logged in.

If it was an error, the user can try to log in again and if that works,
the user becomes active again.

This check is done (at the time of writing) max. every 24 hours. Meaning,
if you managed to sign or use an API token, you have 24 hours to use this
cookie/API token till your user account is checked again in Auth0. To
override this interval change the environment variable
``DJANGO_NOT_BLOCKED_IN_AUTH0_INTERVAL_SECONDS``.

Testing Blocked
===============

To check if a user is blocked, use the ``is-blocked-in-auth0`` which is
development tool shortcut for what the middleware does:

.. code-block:: shell

    $ docker-compose run web python manage.py is-blocked-in-auth0 me@example.com
