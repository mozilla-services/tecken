===================
Tecken System Tests
===================

This directory contains end-to-end tests for Tecken deployments or the local development environment. They can be used to verify the integrity of a deployment. They are also useful to test behaviour that is impossible to test in the unit tests, like headers added by nginx, the actual behaviour of storage backends rather than the behaviour of the emulators or the actual settings used by a deployment. The tests are not intended to duplicate what's in the unit tests, though there may be some overlap in the functionality that's tested. Anything we can sufficiently tested in the unit tests should be tested there.

Running the system tests
========================

The system tests should be run from inside the "web" container to make sure all requirements are avvailable. They are invoked by running pytest in the ``systemtests/`` directory::

    $ make shell
    app@132812ebe909:/app$ cd systemtests/
    app@132812ebe909:/app/systemtests$ pytest --target-env stage

You can enable the tests for large files with the ``--with-large-files`` flag. These tests are slow and store new large files on the target server with each invocation.

Some tests need write access to a GCS bucket, e.g. the upload-by-download tests. To run these tests, you need to store GCP credentials that give the required level of access in ``systemtests/gcp-credentials.json`` and then invoke pytest with the ``--with-bucket-write`` flag. (A key file is available in the Mozilla observability team's 1Password vault.)

You can see all available target environments and custom flags in the "Custom options" section of the ``pytest -h`` output.
