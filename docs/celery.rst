======
Celery
======

.. contents::

Primary Use Case
================

The primary use case for Celery is to be able to upload individual
symbol files to S3/GCS. In Symbol Upload (XXX make link) ``.zip`` files
are uploaded that contain individual files that need to be uploaded
to the appropriate S3/GCS bucket(s).

The default broker is Redis, and in configuration it uses the same
Redis that is used as the default cache backend.


Testing Celery
==============

There's a sample task called ``sample_task``. All it does is that it
sets a key to a value in the cache. That way you can read the cache
after the task has finished to see if the task run successfully.

This ``sample_task`` task is exposed at :base_url:`__task_tester__`
and you have to first make a ``POST`` and then a ``GET``.
For example:

.. code-block:: shell

    $ curl -X POST http://localhost:8000/__task_tester__
    Now make a GET request to this URL
    $ curl http://localhost:8000/__task_tester__
    It works!

Unit Testing with Celery
========================

The ideal pattern is to write tests that test individual tasks directly
rather than testing the views/functions that depend on the task. However,
since in ``conftest.py`` there's a default ``celery_config`` fixture
that enables ``task_always_eager=True`` which means the tasks run
immediately in the same process as the test.
