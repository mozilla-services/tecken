=================
Systemtest README
=================

These test Tecken stage and prod environments.

Contents of this directory::

    bin/         -- directory of scripts
    data/        -- directory for test data
    test_env.sh  -- test runner shell script


Setting up tests
================

Set up the tests this way::

    $ make shell
    root@e62fb7ae586f:/app# cd systemtests
    root@e62fb7ae586f:/app/systemtests# ./setup_tests.py

That creates files in directories under ``data/``.

You only need to set up the tests once to run the system tests against all
environments.


Running tests
=============

First, make sure you have valid, unexpired API tokens for the environment
you're testing.

For destructive tests run in local and stage, you need separate auth tokens for
try uploads with "Upload Try Symbols Files" permissions. See Bug 1759740.

To set auth tokens, add these to your .env file:

* `LOCAL_AUTH_TOKEN`
* `LOCAL_AUTH_TOKEN_TRY`
* `STAGE_AUTH_TOKEN`
* `STAGE_AUTH_TOKEN_TRY`
* `PROD_AUTH_TOKEN`

To run the systemtests, do::

   $ make shell
   root@f09b3cdf8570:/app# cd systemtests/
   root@e62fb7ae586f:/app/systemtests# ./test_env.py ENVIRONMENT

where ``ENVIRONMENT`` is one of the following:

* ``local``: run all tests against your local dev environment
* ``stage``: run all tests against stage
* ``prod``: run non-destructive tests against prod


Rules of systemtest
===================

1. Don't run destructive tests against the prod server environment.

2. Destructive tests get added in ``test_env.py`` in the destructive tests
   section.
