======
Upload
======


History
=======

Symbol upload was originally done in Socorro as part of the
`crash-stats.mozilla.com web app`_.

.. note: As of September 2017, Socorro is still the point where symbol uploads happen.

The *original* way this worked is the same as Tecken except the following key
differences:
Every individual file within the ``.zip`` files are logged in the ORM.


.. _`crash-stats.mozilla.com web app`: https://github.com/mozilla-services/socorro/tree/master/webapp-django/crashstats/symbols


How It Works
============

The upload has to be done with an API token.
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
    >>> url = 'https://symbols.mozilla.org/upload/'
    >>> response = requests.post(url, files=files, headers={'Auth-token': 'xxx'})
    >>> response.status_code
    201

.. note:: Read on for how to upload by posting a URL to a file instead.

Now, on the inside; what happens next
-------------------------------------

Once the ``.zip`` file is uploaded, it's processed. The first part of the
processing is validation. See section below on "Checks and Validation".

Once validation passes, it proceeds to iterate over the files within.
For each file, it queries S3 if the file already exists by the exact same
name and exact same size. If indeed it exists (same name and same size) it
notes it as "skipped" and just logs that filename.
If it does not exist, it proceeds to upload it to S3.

Once the upload processing is complete it creates one ``Upload`` object
and one ``FileUpload`` object for every file that is uploaded to S3.

Upload by download URL
======================

If you have a ``my-symbols.zip`` file on disk, you should HTTPS POST it as
mentioned above. However, a possible optimization is to instead let Tecken
**download** the archive file into itself instead.
If it's already available on a public URL, you can just HTTP POST that URL.
For example:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: xxx' -d url="https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip" https://symbols.mozilla.org/upload/

Or with Python:

.. code-block:: python

    >>> import requests
    >>> url = 'https://symbols.mozilla.org/upload/'
    >>> data = {'url': 'https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip'}
    >>> response = requests.post(url, data=data, headers={'Auth-token': 'xxx'})
    >>> response.status_code
    201


The list of domains that are allowed depends on a whitelist. It's maintained
in the ``DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS`` environment variable and
currently defaults to::

    queue.taskcluster.net
    public-artifacts.taskcluster.net

If you need it to be something else, `file a bug`_.

Note that the whitelist will check redirects. At first a HEAD request is made
with whichever URL you supply. That needs to be whitelisted. If that URL
redirects to a different domain that needs to be whitelisted too.

.. _`file a bug`: https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Symbols

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


Metadata and optimization
=========================

For every gzipped file we upload, we attach 2 pieces of metadata to the key:

    1. Original size
    2. Original MD5 checksum

The reasons for doing this is to be able to quickly skip a file if it's
uploaded a second time.

A similar approach is done for files that *don't* need to be compressed.
In the case of those files, we skip uploading, again, simply if the file
size of an existing file hasn't changed. However, that approach is too
expensive for compressed files. If we don't store and retrieve the
original size and original MD5 checksum, we have to locally compress
the file to be able to make that final size comparison. By instead
checking the original size (and hash) we can skip early without having to
do the compression again.
