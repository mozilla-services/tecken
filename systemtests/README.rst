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
    root@e62fb7ae586f:/app/systemtests# ./setup_tests.sh

That creates files in directories under ``data/``.


Running tests
=============

To run::

   $ make shell
   root@f09b3cdf8570:/app# cd systemtests/
   root@e62fb7ae586f:/app/systemtests# ./test_env.sh ENVIRONMENT

where ``ENVIRONMENT`` is one of the following:

* ``local``: run all tests against your local dev environment
* ``stage``: run all tests against stage
* ``prod``: run non-destructive tests against prod


Rules of systemtest
===================

1. Thou shalt not import anything from ``tecken``. Test code must be
   self-contained.

2. Destructive tests get added in ``test_env.sh`` in the destructive tests
   section.
