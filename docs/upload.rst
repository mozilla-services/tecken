======
Upload
======


History
=======

Symbol upload was originally done in Socorro as part of the
`crash-stats.mozilla.com web app`_.

.. note: As of June 2017, Socorro is still the point where symbol uploads happen.

The original way this worked is the same as Tecken except the following key
differences:

1. Tecken accepts the ``.zip`` upload from the client and responds with
   ``201 Created`` as soon as the upload has been stoved away (still as an archive)
   in S3. A background message queue job starts uploading the individual files.

2. Every individual file within the ``.zip`` files are logged in the ORM.


.. _`crash-stats.mozilla.com web app`: https://github.com/mozilla-services/socorro/tree/master/webapp-django/crashstats/symbols


How It Works
============

The upload has to be done with an API token (FIXME: Need to document this more).
Not only is it important to secure the upload, we also remember *who* made
every symbol upload. This way you can find out what email uploaded what
file when. The user associated with that API token needs to have the permission
``upload.add_upload``.


The upload is done with a ``multipart/form-data`` HTTP POST request.
With ``curl`` it can look like this:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: xxx' --form myfile.zip=@myfile.zip https://symbols.mozilla.org/upload/

Or if you do it in Python ``requests``:

.. code-block:: python

    >>> import requests
    >>> files = {'myfile.zip': open('path/to/myfile.zip', 'rb')}
    >>> response = requests.post(url, files=files, headers={'Auth-token': 'xxx'})
    >>> response.status_code
    201

Now, on the inside; what happens next
-------------------------------------

Once the ``.zip`` file is uploaded, it's immediately uploaded to S3. It's
uploaded into S3 in a special folder called ``inbox/``. If that works,
we write this down in the ORM by creating an ``Upload`` instance.
This contains information about which bucket (see next section) it got
uploaded to, the key name (aka. file path), and a host of additional metadata
such as date, who and size.

When the ``.zip`` is uploaded into the "inbox" folder, the key name
is determined by today's date, a md5 hash of the ``.zip`` file's content as a
string listing and the orignal file as it was called when uploaded.
So an example key name to the inbox is ``inbox/2017-05-06/51dc30ddc473/myfile.zip``.

That ``Upload`` instance's ID is then sent to a
message queue task. What that task does is that it then downloads the ``.zip``
from the inbox, unpacks it into memory, then iterates over the files within
and uploads each and every one to S3. It might seen counter productive to first
upload, then download it again but the message queue tasks run as completely
separate processes so they can't share memory. And S3 is preferred instead of
relying on disk.

The path of the uploaded files exactly match their path in the
``.zip`` file. E.g. If you upload a zip file with a file within called
``symbol.pdb/B33F4A641F154EC4A87E31CCF30F95441/symbol.sym`` it will be
put into S3 as
``{settings.UPLOAD_FILE_PREFIX}/symbol.pdb/B33F4A641F154EC4A87E31CCF30F95441/symbol.sym``.

Once every file has been successfully uploaded, the message queue task
logs it all as individual ``FileUpload`` ORM objects. One for each file, all
foreign keyed to the ``Upload`` object.

Which S3 Bucket
===============

The S3 bucket that gets used for upload is based on a "default" and a
map of exceptions for certain users.

The default is configured as ``DJANGO_UPLOAD_DEFAULT_URL``. For example:
``https://s3-us-west-2.amazonaws.com/org-mozilla-symbols-public``.
From the URL the bucket name is deduced and that's the default S3 bucket used.

The overriding is based on the **uploader's email address**. The default
configuration is to make no exceptions. But you can set
``DJANGO_UPLOAD_URL_EXCEPTIONS`` as a Python dict like this:

.. code-block:: shell

    $ export DJANGO_UPLOAD_URL_EXCEPTIONS={'*@adobe.com': 'https://s3.amazonaws.com/private-bucket'}


Checks and Validations
======================

When you upload your ``.zip`` file the first check is to see that it's a valid
ZIP file that can be extracted into at least 1 file.

The next check is that it iterates over the files within and checks if any
file contains the list of strings in ``settings.DISALLOWED_SYMBOLS_SNIPPETS``.
This check is a blacklist check and its purpose is to assert, for example,
that proprietary files are never uploaded in S3 buckets that might be exposed
publicly.

To override this amend the ``DJANGO_DISALLOWED_SYMBOLS_SNIPPETS`` environment
variable as a comma separated list. But be aware to include the existing
defaults which can be seen in ``settings.py``.

The final check is that each file path in the zip file matches the
pattern ``<module>/<hex>/<file>`` or ``<name>-symbols.txt``. All other
file paths are rejected.


Gzip
====

Certain files get gzipped before being uploaded into S3. At the time of writing
that list is all ``.sym`` files. S3, unlike something like Nginx, doesn't do
content encoding on the fly based on the client's capabilities. Instead,
we manually gzip the file in memory in Tecken and set the additional
``ContentEncoding`` header to ``gzip``. Since these ``.sym`` files are
always text based, it saves a lot of memory in the S3 storage.

Additionally, the ``.sym`` files get their content type (aka. mime type)
set when uploading to S3 to ``text/plain``.
Because S3 can't know in advance that the files
are actually ASCII plain text, if you try to open them in a browser it will
set the ``Content-Type`` to ``application/octet-stream`` which makes it
hard to quickly look at its content in a browser.

Both the gzip and the mimetype overrides can be changed by setting the
``DJANGO_COMPRESS_EXTENSIONS`` and ``DJANGO_MIME_OVERRIDES`` environment
variables. See ``settings.py`` for the current defaults.
