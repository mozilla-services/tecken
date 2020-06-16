======
Upload
======

History
=======

Prior to 2018, Symbol upload was originally done in Socorro as part of Crash Stats.
Now it's handled by Tecken in much the same way except Tecken additionally logs
every individual file inside the ZIP file in the ORM.


.. _upload-basics:

Uploading basics
================

Uploading requires special permission. The process for requesting access to
upload symbols is roughly the following:

1. `Create a bug <https://bugzilla.mozilla.org/enter_bug.cgi?format=__standard__&product=Socorro&component=Tecken>`
   requesting access to upload symbols.

2. A Tecken admin will process the request.

   If you are a Mozilla employee, your manager will be needinfo'd to verify you need
   upload access.

   If you are not a Mozilla employee, we'll need to find someone to vouch for you.

3. After that's been worked out, the Tecken admin will give you permission to upload
   symbols.


Once you have permission to upload symbols, you will additionally need an API token.
Once you log in, you can `create an API token <https://symbols.mozilla.org/tokens>`_.
It needs to have the "Upload Symbols" permission.


How to upload by HTTP POST
==========================

Uploads by HTTP POST must have a ``multipart/form-data`` payload with a ZIP
file containing the symbols files.

Here's a ``curl`` example:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: xxx' --form myfile.zip=@myfile.zip https://symbols.mozilla.org/upload/

Here's a ``Python`` example using ``requests``:

.. code-block:: python

    >>> import requests
    >>> files = {'myfile.zip': open('path/to/myfile.zip', 'rb')}
    >>> url = 'https://symbols.mozilla.org/upload/'
    >>> response = requests.post(url, files=files, headers={'Auth-token': 'xxx'})
    >>> response.status_code
    201


How to upload by download URL
=============================

Instead of uploading the symbols file by HTTP POST, you can POST the url to
where the symbols file is and Tecken will download the file from that location
and process it.

This is helpful if the symbols file is very big and is already available at a
publicly available URL.

An example with ``curl``:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: xxx' -d url="https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip" https://symbols.mozilla.org/upload/

An example with ``Python`` and the ``requests`` library:

.. code-block:: python

    >>> import requests
    >>> url = 'https://symbols.mozilla.org/upload/'
    >>> data = {'url': 'https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip'}
    >>> response = requests.post(url, data=data, headers={'Auth-token': 'xxx'})
    >>> response.status_code
    201


Domains that Tecken will download from is specified in the
``DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS`` environment variable and at the time
of this writing is set to::

    queue.taskcluster.net
    public-artifacts.taskcluster.net

If you need another domain supported,
`file a bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Tecken>`_.

Note that Tecken will check redirects. At first a HEAD request is made with the
URL and Tecken will check both the original URL and the redirected URL against
the list of allowed URLs.

Symbols processing
==================

Once the ``.zip`` file is uploaded, it's processed. The first part of the
processing is validation. See section below on "Checks and Validation".

Once validation passes, it proceeds to iterate over the files within.
For each file, it queries S3 if the file already exists by the exact same
name and exact same size. If indeed it exists (same name and same size) it
notes it as "skipped" and just logs that filename.
If it does not exist, it proceeds to upload it to S3.

Once the upload processing is complete it creates one ``Upload`` object
and one ``FileUpload`` object for every file that is uploaded to S3.

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
This check is a block list check and its purpose is to assert, for example,
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


Metadata and Optimization
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


Try Builds
==========

A Try build is a build of Firefox that isn't necessarily triggered by
landing a patch in ``mozilla-central``. The access model for triggering
Try builds is much more relaxed. Try builds generate symbols that are
useful to have for debugging too. However, because of the difference in
access rights, it's important that symbols from Try builds aren't
allowed to override symbols from non-Try builds. For this reason,
Tecken uploads all symbols from Try builds in a different S3
configuration.

.. note: At the moment, symbols from Try builds go into the same S3 bucket but into a different root prefix.

Another important difference between a Try build and a non-Try build is
that the symbols are much less likely to be useful for a long time.
A developer might be testing something out for a couple of days, do some
debugging and then move on to something else. Therefore we don't save
the Try build symbols for equally long in AWS S3.

So how do you distinguish between symbols from a Try build and those
from a non-Try build?

1. By the API token's permission, or,

2. Explicitly passing the ``try`` POST key with a non-empty value.

If you upload symbols with the frontend, there's a checkbox to indicate
that it's from a Try build. It's unchecked by default.

To upload by API key permission, create a new API Token and when you
select permission to associate with it, select ``Upload Try Symbols Files``.
This is how the backend knows to associate this upload with the files
coming from a Try build.

There's an override though. You can manually set the key-value ``try``.
Like this:

.. code-block:: shell

    $ curl -X POST -H 'auth-token: xxx' --form try=true --form myfile.zip=@myfile.zip https://symbols.mozilla.org/upload/

See the :ref:`Try builds <download-try-builds>` documentation under **Download**.
