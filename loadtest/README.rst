===============
Eliot load test
===============

This is an Eliot load test. It uses molotov.

.. Note::

   This isn't used frequently and isn't actively maintained, so it's likely
   you'll have to update it when you use it.


Setup
=====

First run::

    make build

That builds the virtual environment with the libraries you need to build
and run the load test.

Then run::

    make buildstacks

That builds stack data that's used in the load test.

Once you've built the environment and built some stacks, you can run the
various test types.


Running
=======

Run::

    make smoketest

This runs a single worker for 10 seconds and lets you know if the system is
working at all.

Run::

    make loadtest

This runs a load test for 10 minutes. This is long enough to force scaling up.
Ctrl-C if you want to stop early.

Run::

    make size

This autosizes molotov by starting with minimal workers and ramping up over
time.
