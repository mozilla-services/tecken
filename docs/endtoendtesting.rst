==================
End-to-End Testing
==================

Overview
========

There is no automated end-to-end testing that triggers on post-deploy steps
or anything like that. Mozilla Infrasec will continually check that our
server responds with the right security headers. However, there are some
noted techniques for testing.

Uploads
=======

To run this, you need to have access and permissions to Prod
(``symbols.mozilla.org``) **and** Stage (``https://symbols.stage.mozaws.net``).
Go to Prod and grab (or create) an API token with permission:
``View All Symbols Uploads``. For Stage, grab (or create) an API token
with permission: ``Upload Symbols Files``. Then run the following script
like this:

.. code-block:: shell

    $ ./bin/end-to-end-test-symbol-upload.py --help
    $ ./bin/end-to-end-test-symbol-upload.py PRODTOKEN STAGETOKEN

It all goes well, it will find the most recent upload on Prod that uses
the "Upload by Download URL" and send that URL to Stage. If all goes well
it will output something like this:

.. code-block:: shell

    Stage user: pbengtsson@example.com
    Prod user: pbengtsson@example.com
    About to upload 916.6MB as URL to Stage.

    Took 3.5 minutes
    Files skipped: 0
    Files uploaded: 72
    Files uploaded, completed: 72

    To see it, go to: https://symbols.stage.mozaws.net/uploads/upload/1186

    It worked! 🎉 🎊 👍🏼 🌈
