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


Tecken consists of:

1. a webapp (also called Tecken) that covers uploading and downloading symbols
2. a webapp (Eliot) that covers symbolication

To run these two services, do:

.. code-block:: shell

   $ make run


The Tecken webapp is at: http://localhost:3000

Eliot is at: http://localhost:8050


Managing dependencies
=====================

Python dependencies
-------------------

Python dependencies are maintained in the ``requirements.in`` file and
"compiled" with hashes and dependencies of dependencies in the
``requirements.txt`` file.

To add a new dependency, add it to the file and then do::

   $ make shell
   $ pip-compile --generate-hashes

Then rebuild your docker environment::

  $ make build

If there are problems, it'll tell you.


JavaScript dependencies (Tecken webapp)
---------------------------------------

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

Tecken webapp and Eliot both have Python unit tests that use the `pytest
<https://pytest.org/>`_ test framework.

To run all of the unit tests, do:

.. code-block:: shell

   $ make test


See :ref:`dev-tecken-tests` and :ref:`dev-eliot-tests` for details.


System tests
------------

System tests are located in the repository in ``systemtests/``. See the
``README.rst`` there for usage.

System tests can be run against any running environment: local, stage, or prod.


Tecken webapp things
====================

When running the Tecken webapp in the local dev environment, it's at:
http://localhost:3000

The code is in ``tecken/``.

You can override Tecken webapp configuration in your ``.env`` file.


.. _dev-tecken-tests:

Python tests for Tecken webapp
------------------------------

To run the tests, do:

.. code-block:: shell

   $ make test

Tests for the Tecken webapp go in ``tecken/tests/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ make testshell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ cd tecken/
   app@xxx:/app/tecken$ pytest tests/test_download.py


JavaScript tests
----------------

The Tecken webapp is built using JavaScript and React. There are no tests for
this code and it has to be tested manually. You can do something like this:

1. go to Tecken webapp website
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


Database migrations
-------------------

The Tecken webapp uses Django's ORM and thus we do database migrations using
Django's migration system.

Do this::

   $ make shell
   app@xxx:/app$ ./manage.py makemigration --name "BUGID_desc" APP


Accounts and first superuser
----------------------------

The Tecken webapp has an accounts system. Users need to create their own API
tokens but before they can do that they need to be promoted to have that
permission at all. The only person/people who can give other users permissions
is the superuser. To bootstrap the user administration you need to create at
least one superuser.  That superuser can promote other users to superusers too.

This action does NOT require that the user signs in at least once. If the
user does not exist, it gets created.

The easiest way to create your first superuser is to use ``docker-compose``:

.. code-block:: shell

    docker-compose run --rm web bash python manage.py superuser yourname@example.com

Additionally, in a local development environment, you can create a
corresponding user in the oidcprovider service like this:

.. code-block:: shell

   docker-compose exec oidcprovider /code/manage.py createuser yourname yourpassword yourname@example.com


Giving users permission to upload symbols
-----------------------------------------

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


Viewing all metrics keys
------------------------

In the Tecken webapp, to get insight into all metrics keys that are used, a
special Markus backend is enabled called
``tecken.markus_extra.LogAllMetricsKeys``. It's enabled by default in local
development. And to inspect its content you can either open
``all-metrics-keys.json`` directly (it's git ignored) or you can run:

.. code-block:: shell

    $ make shell
    app@xxx:/app$ ./bin/list-all-metrics-keys.py

Now you can see a list of all keys that are used. Take this and, for example,
make sure you make a graph in Datadog of each and everyone. If there's a key
in there that you know you don't need or care about in Datadog, then delete
it from the code.

The file ``all-metrics-keys.json`` can be deleted any time and it will be
recreated again.


Minio (S3 mock server)
----------------------

When doing local development we, by default, mock AWS S3 and instead use
`minio`_. It's API compatible so it should reflect how AWS S3 works but
with the advantage that you don't need an Internet connection and real
S3 credentials just to test symbol uploads for example.

When started with docker, it starts a web server on ``:9000`` that you can
use to browse uploaded files. Go to ``http://localhost:9000``.

.. _`minio`: https://minio.io/


How to do local Upload by Download URL
--------------------------------------

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


Debugging a "broken" Redis
--------------------------

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


Auth debugging
--------------

Cache/cookeis issues
~~~~~~~~~~~~~~~~~~~~

Anyone can test caching and cookies by going to
`<https://symbols.mozilla.org/__auth_debug__>`_.  That's a good first debugging
step for helping users figure out auth problems.


Auth0 issues
~~~~~~~~~~~~

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


Testing if a user is blocked
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To check if a user is blocked, use the ``is-blocked-in-auth0`` which is
development tool shortcut for what the middleware does:

.. code-block:: shell

    $ docker-compose run web python manage.py is-blocked-in-auth0 me@example.com


Eliot things
============

How Eliot works
---------------

When running Eliot in the local dev environment, it's at: http://localhost:8050

The code is in ``eliot-service/``.

Eliot logs its configuration at startup. You can override any of those
configuration settings in your ``.env`` file.

Eliot runs in a Docker container and is composed of:

* `Honcho <https://honcho.readthedocs.io/>`_ process which manages:

  * eliot_web: `gunicorn <https://docs.gunicorn.org/en/stable//>`_ which runs
    multiple worker webapp processes
  * eliot_disk_manager: a disk cache manager process

Symbolication requests come in and are handled by the Eliot webapp. It pulls
sym files from the urls configured by ``ELIOT_SYMBOL_URLS``. By default, that's
``https://symbols.mozilla.org/try``.

The Elliot webapp downloads sym files, parses them into symcache files, and
performs symbol lookups with the symcache files. Parsing sym files and
generating symcache files takes a long time, so it stores the symcache files in
a disk cache shared by all webapp processes running in that Docker container.
The disk cache manager process deletes least recently used items from the disk
cache to keep it under ``ELIOT_SYMBOLS_CACHE_MAX_SIZE`` bytes.


.. _dev-eliot-metrics:

Metrics
-------

.. autometrics:: eliot.libmarkus.ELIOT_METRICS


.. _dev-eliot-tests:

Python tests for Eliot
----------------------

To run the tests, do:

.. code-block:: shell

   $ make test

Tests for the Tecken webapp go in ``tecken/tests/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ make testshell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ cd tecken/
   app@xxx:/app/tecken$ pytest tests/test_download.py
