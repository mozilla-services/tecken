==================
Smoke tests README
==================

These test Tecken stage and prod environments.

Contents of this directory::

    bin/         -- directory of scripts
    data/        -- directory for test data
    test_env.sh  -- test runner shell script


Setting up tests
================

Before running the smoke tests, you need to `build a local dev environment
<https://tecken.readthedocs.io/en/latest/dev.html>`__.

Then set up the tests this way::

    $ just shell
    root@e62fb7ae586f:/app# cd smoketests
    root@e62fb7ae586f:/app/smoketests# ./setup_tests.py

That creates files in directories under ``data/``.

You only need to set up the tests once to run the smoke tests against all
environments.


Running tests
=============

The smoke tests are run using the ``test_env.py`` Python script. You can get
help about the command-line invocation of that script using::

    $ just shell
    root@e62fb7ae586f:/app# cd smoketests
    root@e62fb7ae586f:/app/smoketests# ./test_env.py --help

The help includes a list of available environments.

You need to make sure you have valid, unexpired API tokens for the environment
you're testing. Add these tokens to your ``.env`` file using the environment
variable names in the help output, e.g. ``STAGE_AUTH_TOKEN`` and
``STAGE_AUTH_TOKEN_TRY`` for the stage environment.

For destructive tests run in local and stage, you need separate auth tokens for
try uploads with "Upload Try Symbols Files" permissions. See Bug 1759740.

To run the smoke tests, do::

    root@e62fb7ae586f:/app/smoketests# ./test_env.py <ENV_NAME>


Rules of smoke tests
====================

1. Don't run destructive tests against the prod server environment.

2. Destructive tests get added in ``test_env.py`` in the destructive tests
   section.
