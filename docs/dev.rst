===========
Development
===========

.. contents::
   :local:


Setup quickstart
================

1. Install required software: Docker, make, and git.

   **Linux**:

       Use your package manager.

   **OSX**:

       Install `Docker for Mac <https://docs.docker.com/docker-for-mac/>`_.

       Use `homebrew <https://brew.sh>`_ to install make and git:

       .. code-block:: shell

          $ brew install make git

   **Other**:

       Install `Docker <https://docs.docker.com/engine/installation/>`_.

       Install `make <https://www.gnu.org/software/make/>`_.

       Install `git <https://git-scm.com/>`_.

2. Clone the repository so you have a copy on your host machine.

   Instructions for cloning are `on the Tecken page in GitHub
   <https://github.com/mozilla-services/tecken>`_.

3. (*Optional for Linux users*) Set UID and GID for Docker container user.

   If you're on Linux or you want to set the UID/GID of the app user that
   runs in the Docker containers, run:

   .. code-block:: shell

      $ make .env

   Then edit the file and set the ``APP_UID`` and ``APP_GID`` variables. These
   will get used when creating the app user in the base image.

   If you ever want different values, change them in ``.env`` and re-run
   ``make build``.

4. Build Docker images for Socorro services.

   From the root of this repository, run:

   .. code-block:: shell

      $ make build

   That will build the app Docker image required for development.

5. Initialize Postgres and S3 (localstack) / GCS (gcs-emulator).

   Run:

   .. code-block:: shell

      $ make setup

   This creates the Postgres database and sets up tables, integrity rules, and
   a bunch of other things.

   For S3/GCS, this creates the required buckets.

Tecken consists of Symbols Service webapp that covers uploading and downloading symbols.

To run the webapp service, do:

.. code-block:: shell

   $ make run


The Symbols Service webapp is at: http://localhost:3000


How to
======

How to set up a development container for VS Code
-------------------------------------------------

The repository contains configuration files to build a
`development container <https://containers.dev/>`_ in the `.devcontainer`
directory. If you have the "Dev Containers" extension installed in VS Code, you
should be prompted whether you want to reopen the folder in a container on
startup. You can also use the "Dev containers: Reopen in container" command
from the command palette. The container has all Python requirements installed.
IntelliSense, type checking, code formatting with Ruff and running the tests
from the test browser are all set up to work without further configuration.

VS Code should automatically start the container, but it may need to be built on
first run:

.. code-block:: shell

   $ make devcontainerbuild


What services are running in a local dev environment
----------------------------------------------------

============  ====  =============================================
service       port  description
============  ====  =============================================
frontend      3000  Javascript proxy for webapp--use with browser
web           8000  Django webapp--use with APIs
localstack    4566  S3 emulation service
gcs-emulator  4443  GCS emulation service
db            5432  Postgres database
redis         6379  Redis service
fakesentry    8090  Sentry emulation service
oidcprovider  8080  SSO emulation service
statsd        8081  Grafana / statsd
============  ====  =============================================


How to change settings in your local dev environment
----------------------------------------------------

Edit the ``.env`` file and add/remove/change settings. These environment
variables are used by make and automatically included by docker compose.

If you are using a VS Code development container for other repositories such as
`eliot <https://github.com/mozilla-services/eliot>`_ or
`socorro <https://github.com/mozilla-services/socorro>`_, you may need to
change the default ports exposed by docker compose to avoid conflicts with
similar services, for example:

.. code-block:: shell

   EXPOSE_TECKEN_PORT=8200
   EXPOSE_LOCALSTACK_PORT=4567
   EXPOSE_SENTRY_PORT=8290
   EXPOSE_OIDC_PORT=8280
   EXPOSE_STATSD_PORT=8281
   EXPOSE_GCS_EMULATOR_PORT=4443

If you are using a development container for VS Code, you make need to restart
the container to pick up changes:

.. code-block:: shell

   $ make devcontainer


How to create a script to recreate your local dev environment
-------------------------------------------------------------

Run:

.. code-block:: shell

   $ make slick.sh

Then edit the ``slick.sh`` script filling in:

* a username
* a password
* an email address

None of these matter except that you need them to enter values into the SSO
emulation service when you log into your Tecken local dev environment.

You can use ``slick.sh`` to recreate your local dev environment, create a
superuser account, and create an API token. This simplifies setting everything
up when you're switching contexts or testing things.

.. code-block:: shell

   $ ./slick.sh
   [gobs of output here]


How to use the webapp
---------------------

The Tecken webapp in the local dev environment is split into two
containers:

* frontend: (localhost:3000) a Javascript proxy that serves up-to-date
  Javascript and CSS files
* web: (localhost:8000) the Django webapp

To connect to the webapp in your browser, use ``http://localhost:3000``.

To use a webapp API, use ``http://localhost:8000``.


How to create a superuser account from the command line
-------------------------------------------------------

You need to create an account in two places: the oidcprovider (our SSO
emulation service) and in the Tecken webapp.

.. code-block:: shell

   # Run these from the host

   # This creates an SSO account in the oidcprovider
   $ docker compose exec oidcprovider /code/manage.py createuser FAKEUSERNAME FAKEPASSWORD FAKEEMAIL

   # This creates a superuser account in the Tecken webapp
   $ docker compose run --rm web bash python manage.py superuser FAKEEMAIL

.. Note::

   The oidcprovider account will persist until the ``oidcprovider`` container is
   stopped.


How to create an account from the webapp
----------------------------------------

To log in, do this:

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
You can visit http://localhost:8080/account/logout to manually log out.


How to create an API token from the command line
------------------------------------------------

.. code-block:: shell

   # Run this from the host

   $ docker compose run --rm web bash python manage.py createtoken EMAIL TOKEN

Tokens are 32 character hex strings. You can create one in Python:

>>> import uuid
>>> uuid.uuid4().hex
'64cfcc37088e43909168739bc7369197'

.. Note::

   Tokens can include an optional hyphen and comment at the end to make
   it easier to distinguish tokens.

   Examples::

       # No comment
       c7c1f8cab79545b6a06bc4122f0eb3cb

       # With comment
       c7c1f8cab79545b6a06bc4122f0eb3cb-localdevtoken


How to create a new database migration
--------------------------------------

The Symbols Service webapp uses Django's ORM and thus we do database migrations
using Django's migration system.

Do this:

.. code-block:: shell

   $ make shell
   app@xxx:/app$ ./manage.py makemigration --name "BUGID_desc" APP


How to manipulate the local dev environment S3 bucket
-----------------------------------------------------

We use `localstack <https://github.com/localstack/localstack>`__ for S3
emulation.

Use the ``bin/s3_cli.py`` script:

.. code-block:: shell

   $ make shell
   app@xxx:/app$ ./bin/s3_cli.py --help
   Usage: s3_cli.py [OPTIONS] COMMAND [ARGS]...

     Local dev environment S3 manipulation script and bargain emporium.

   Options:
     --help  Show this message and exit.

   Commands:
     create        Creates a bucket
     delete        Deletes a bucket
     list_buckets  List S3 buckets
     list_objects  List contents of a bucket


How to manipulate the local dev environment GCS bucket
------------------------------------------------------

We use `fake-gcs-server <https://github.com/fsouza/fake-gcs-server>`__ for GCS
emulation.

Use the ``bin/gcs_cli.py`` script:

.. code-block:: shell

   $ make shell
   app@xxx:/app$ ./bin/gcs_cli.py --help
   Usage: gcs_cli.py [OPTIONS] COMMAND [ARGS]...

   Local dev environment GCS manipulation script

   Options:
     --help  Show this message and exit.

   Commands:
     create        Creates a bucket
     delete        Deletes a bucket
     list_buckets  List GCS buckets
     list_objects  List contents of a bucket


How to access the database
--------------------------

We use postgresql. To open a psql shell, do:

.. code-block:: shell

   $ make psql
   NOTE: Password is 'postgres'.
   /usr/bin/docker compose run --rm db psql -h db -U postgres -d tecken
   Password for user postgres:
   psql (12.7 (Debian 12.7-1.pgdg100+1))
   Type "help" for help.

   tecken=#

Note that it tells you the password to use.


Bugs / Issues
=============

All bugs are tracked in `Bugzilla <https://bugzilla.mozilla.org/>`_.

Write up a new bug:

https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General

If you want to do work for which there is no bug, it's best to write up a bug
first. Maybe the ensuing conversation can save you the time and trouble
of making changes!


Code workflow
=============

Bugs
----

Either write up a bug or find a bug to work on.

Assign the bug to yourself.

Work out any questions about the problem, the approach to fix it, and any
additional details by posting comments in the bug.


Pull requests
-------------

Pull request summary should indicate the bug the pull request addresses. Use a hyphen between "bug" and the bug ID(s). For
example::

    bug-nnnnnnn: removed frog from tree class

For multiple bugs fixed within a single pull request, list the bugs out individually. For example::

   bug-nnnnnnn, bug-nnnnnnn: removed frog from tree class

Pull request descriptions should cover at least some of the following:

1. what is the issue the pull request is addressing?
2. why does this pull request fix the issue?
3. how should a reviewer review the pull request?
4. what did you do to test the changes?
5. any steps-to-reproduce for the reviewer to use to test the changes

After creating a pull request, attach the pull request to the relevant bugs.

We use the `rob-bugson Firefox addon
<https://addons.mozilla.org/en-US/firefox/addon/rob-bugson/>`_. If the pull
request has "bug-nnnnnnn: ..." or "bug-nnnnnnn, bug-nnnnnnn: ..." in the summary, then rob-bugson will see that
and create a "Attach this PR to bug ..." link.

Then ask someone to review the pull request. If you don't know who to ask, look
at other pull requests to see who's currently reviewing things.


Code reviews
------------

Pull requests should be reviewed before merging.

Style nits should be covered by linting as much as possible.

Code reviews should review the changes in the context of the rest of the system.


Landing code
------------

Once the code has been reviewed and all tasks in CI pass, the pull request
author should merge the code.

This makes it easier for the author to coordinate landing the changes with
other things that need to happen like landing changes in another repository,
data migrations, configuration changes, and so on.

We use "Rebase and merge" in GitHub.


Conventions
===========

Python code conventions
-----------------------

All Python code files should have an MPL v2 header at the top::

  # This Source Code Form is subject to the terms of the Mozilla Public
  # License, v. 2.0. If a copy of the MPL was not distributed with this
  # file, You can obtain one at http://mozilla.org/MPL/2.0/.


We use `ruff <https://docs.astral.sh/ruff/>`_ to reformat Python
code and we use `prettier <https://prettier.io/>`_ to reformat JS code.


To lint all the code, do:

.. code-block:: bash

   $ make lint


To reformat all the code, do:

.. code-block:: bash

   $ make lintfix


HTML/CSS conventions
--------------------

2-space indentation.


Javascript code conventions
---------------------------

2-space indentation.

All JavaScript code files should have an MPL v2 header at the top::

  /*
   * This Source Code Form is subject to the terms of the Mozilla Public
   * License, v. 2.0. If a copy of the MPL was not distributed with this
   * file, You can obtain one at http://mozilla.org/MPL/2.0/.
   */


Git conventions
---------------

First line is a summary of the commit. It should start with the bug number. Use a hyphen between "bug" and the bug ID(s). For example::

   bug-nnnnnnn: summary

For multiple bugs fixed within a single commit, list the bugs out individually. For example::

   bug-nnnnnnn, bug-nnnnnnn: summary

After that, the commit should explain *why* the changes are being made and any
notes that future readers should know for context or be aware of.


Managing dependencies
=====================

Python dependencies
-------------------

Python dependencies are maintained in the ``requirements.in`` file and
"compiled" with hashes and dependencies of dependencies in the
``requirements.txt`` file.

To add a new dependency, add it to the file and then do:

.. code-block:: shell

   $ make rebuildreqs

Then rebuild your docker environment:

.. code-block:: shell

   $ make build

If there are problems, it'll tell you.

In some cases, you might want to update the primary and all the secondary
dependencies. To do this, run:

.. code-block:: shell

   $ make updatereqs


JavaScript dependencies (Symbols Service)
-----------------------------------------

Tecken uses `yarn <https://yarnpkg.com/>`_ for JavaScript dependencies. Use the
``yarn`` installed in the Docker frontend container:

.. code-block:: shell

   $ docker compose run frontend bash

   # display packages that can be upgraded
   node@xxx:/app$ yarn outdated

   # example of upgrading an existing package
   node@xxx:/app$ yarn upgrade date-fns --latest

   # example of adding a new package
   node@xxx:/app$ yarn add some-new-package

When you're done, you have to rebuild the frontend Docker container:

.. code-block:: shell

   $ docker compose build frontend

Your change should result in changes to ``frontend/package.json`` *and*
``frontend/yarn.lock`` which needs to both be checked in and committed.


Documentation
=============

Documentation for Tecken is build with `Sphinx
<http://www.sphinx-doc.org/>`_ and is available on ReadTheDocs.

To build the docs, do:

.. code-block:: shell

   $ make docs

Then view ``docs/_build/html/index.html`` in your browser.


Testing
=======

Python tests for Symbols Service webapp
---------------------------------------

Tecken uses the `pytest <https://pytest.org/>`_ test framework.

To run the tests, do:

.. code-block:: shell

   $ make test

Tests for the Symbols Service webapp go in ``tecken/tests/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ make testshell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ cd tecken/
   app@xxx:/app/tecken$ pytest tests/test_download.py

   <pytest output>


JavaScript tests
----------------

The Tecken webapp is built using JavaScript and React. There are no tests for
this code and it has to be tested manually. You can do something like this:

1. go to Tecken webapp website
2. wait for front page to load
3. click on "Home"
4. click on "Help"
5. click on "Log in" and log in
6. click on "Home"
7. click on "User management"
8. click on "API tokens"
9. click on "Uploads"
10. click on "Help"
11. click on "Sign out"


System tests
------------

System tests are located in the repository in ``systemtests/``. See the
``README.rst`` there for usage.

System tests can be run against any running environment:

* local: local dev environment
* stage: the stage server environment
* prod: the prod server environment--will not run destructive tests

System tests can help verify that upload API and download API work. They
periodically need to be updated as symbols files expire out of the systems.


Load tests
----------

At various points, we've done some load testing of the system. The scripts are
located in:

https://github.com/mozilla-services/tecken-loadtests/

They're generally unmaintained, but can be a good starting point for a new load
testing effort.


How to do local Upload by Download URL
======================================

.. Note::

   This may need to be updated.

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
and one outside in the ``tecken-loadtests`` directory on your host.


Debugging a "broken" Redis
==========================

.. Note::

   This may need to be updated.

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
==============

.. Note::

   This may need to be updated.

Cache/cookies issues
--------------------

Anyone can test caching and cookies by going to
`<https://symbols.mozilla.org/__auth_debug__>`_.  That's a good first debugging
step for helping users figure out auth problems.


Auth0 issues
------------

Symbols Service uses Mozilla SSO. Anyone can log in, but by default accounts
don't have special permissions to anything.

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
----------------------------

To check if a user is blocked, use the ``is-blocked-in-auth0`` which is
development tool shortcut for what the middleware does:

.. code-block:: shell

   $ docker compose run web python manage.py is-blocked-in-auth0 me@example.com
