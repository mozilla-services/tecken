======
Celery
======

.. contents::

Primary Use Case
================

Celery is used for the following tasks:

1. Every time an upload is made, a piece of code is triggered that
   counts how many uploads have been done in that UTC 24 day. This
   populates the ``UploadsCreated`` model. By querying that you can
   see how much was uploaded by date rather than having to do heavy
   aggregates on the main ``Upload`` model.

2. Every time a symbol URL is attempted to be retrieved but we find out
   it's not in our storage backend, we need to write this down in the
   database. We do that by calling ``store_missing_symbol`` which is
   synchronous. However, if any operational error happens, instead of
   giving up we send the same parameters to a wrapped function that runs
   as a Celery task. That task is wrapped with a patient decorator that
   retries repeatedly.
   Note that all of this is "guarded" by a memoization wrapper that tries
   to make sure we only all of this only happens once per 24 per
   symbol signature.


Testing Celery
==============

For more information about how to end-to-end test the Celery tasks see the
:ref:`End-to-end testing Celery <endtoendtesting-celery>` section.

Unit Testing with Celery
========================

The ideal pattern is to write tests that test individual tasks directly
rather than testing the views/functions that depend on the task. However,
since in ``conftest.py`` there's a default ``celery_config`` fixture
that enables ``task_always_eager=True`` which means the tasks run
immediately in the same process as the test.
