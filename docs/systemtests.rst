============
System Tests
============

About
=====

System test aims to replace and be similar to doing manual testing with
``curl``. They depend on the server being up and running
but will start a web server if it's not already running.
To start the system tests run:

.. code-block:: shell

    $ make systemtest

If you want to see the requests coming in in foreground logging, you can
start the server in another terminal first, and then run ``make systemtest``
in a second terminal.

If you need to do some debugging into a specific test with system tests,
it's tedious to have to run all the tests every time. One trick is to
take the command that ``make systemtest`` represents in ``Makefile``
and then run it with extra ``pytest`` parameters. For example:

.. code-block:: shell

    $ docker-compose run systemtest tests/systemtest/run_tests.sh -k test_delberately_404ing_and_csv_reporting

.. note:: If the systemtests fail when you run them locally it's most likely
          because you haven't uploaded the symbol fixtures necessary.
          See the next section about **Stymbol fixtures**.


Symbol fixtures
===============

The systemtests *assume* that certain symbols are in your
S3 storage already. This is fine for the Production environment but
problematic for Dev and Stage and your local development environment.

For Dev and Stage the S3 buckets they depend on have already been "primed"
to have all the symbols as of August 2017. So they should exist in their S3
buckets.

However, for local development we run a mocking S3 server which is not
persistent between restarts. To prime it you need to upload the file:
``tests/systemtests/symbols-for-systemtests.zip``. To do that you need an
API token. So make sure you can start the frontend and sign in and generate
API tokens. Once you have your API token, start the server (``make run``) and
upload the file like this:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: TOKENTOKENTOKEN' --form myfile.zip=@tests/systemtests/symbols-for-systemtests.zip http://localhost:8000/upload/

If you're hacking on the system tests and decide to depend on more real symbol
fixtures you can re-generate the ``symbols-for-systemtests.zip`` file using
the script ``tests/systemtests/download-old-symbols.py`` accordingly.


Deployment and purpose
======================

The primary purpose of system tests is to test the built system just prior to
deployment. The deployment pipeline builds the relevant docker containers
and just before deciding to put them into AWS it runs the system tests.

But the system tests are also useful for local development. There's nothing
that they do that there isn't a unit test for but it's healthy to run to
make sure all running parts can talk to each other. For the example, the
system tests do actually trigger a Celery background job and it checks that
it was processed by the Celery worker.

It also checks that the web app can talk to the S3 mocking server and it
uses the Redis caches to actually store and keep things. In non-development
docker it actually talks to a real AWS S3 bucket according to its configuration.
