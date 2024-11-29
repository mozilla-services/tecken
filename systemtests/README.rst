===================
Tecken System Tests
===================

This directory contains end-to-end tests for Tecken deployments or the local development
environment. They can be used to verify the integrity of a deployment. They are also
useful to test behavior that is impossible to test in the unit tests, like headers added
by nginx, the actual behavior of storage backends rather than the behavior of the
emulators or the actual settings used by a deployment. The tests are not intended to
duplicate what's in the unit tests, though there may be some overlap in the
functionality that's tested. Anything we can sufficiently test in the unit tests should
be tested there.

Running the system tests
========================

The system tests should be run from inside the "web" container to make sure all
requirements are available. They are invoked by running pytest in the ``systemtests/``
directory::

    $ make shell
    app@132812ebe909:/app$ cd systemtests/
    app@132812ebe909:/app/systemtests$ pytest --target-env stage

You can enable the tests for large files with the ``--with-large-files`` flag. These
tests are slow and store new large files on the target server with each invocation.

Some tests need write access to a GCS bucket, e.g. the upload-by-download tests. To run
these tests, you need to store GCP credentials that give the required level of access in
``systemtests/gcp-credentials.json`` and then invoke pytest with the
``--with-write-bucket`` flag. (A key file is available in the Mozilla observability
team's 1Password vault.)

You can see all available target environments and custom flags in the "Custom options"
section of the ``pytest -h`` output.

Rules of system tests
=====================

1. Don't import anything from ``tecken``.

2. Tests writing to the fake data bucket must be decorated with
   ``@pytest.mark.write_bucket``.

3. Tests requiring nginx in front of the app must be decorated with
   ``@pytest.mark.nginx``.

4. Tests uploading, and hence potentially destroying, data must be decoarated with
   ``@pytest.mark.upload``. If all tests in a file require uploads, you can also use::

       pytestmark = pytest.mark.upload

   at the top of the file to mark all tests at once.

5. Since there is hardly anything that can be tested without uploading data first,
   the system tests should never be run against a production environment.
