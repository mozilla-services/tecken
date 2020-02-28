=================
Systemtest README
=================

These test Tecken stage and prod environments.

Contents of this directory::

    bin/         -- directory of scripts
    data/        -- directory for test data
    test_env.sh  -- test runner shell script



Running tests
=============

To run::

   $ make shell
   root@f09b3cdf8570:/app# cd systemtests/

To run against local dev environment, do::

   root@f09b3cdf8570:/app/systemtests# ./test_env.sh local

To run against stage, do::

   root@f09b3cdf8570:/app/systemtests# ./test_env.sh stage

To run against prod, do::

   root@f09b3cdf8570:/app/systemtests# ./test_env.sh prod

.. Note::

   When running against prod, the systemtests will not run destructive tests.
   Yay!


Rules of systemtest
===================

1. Thou shalt not import anything from ``tecken``. Test code must be
   self-contained.

2. Thou shalt mark every non-destructive test as such. Don't mark destructive
   tests as non-destructive.
