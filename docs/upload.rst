=================
Uploading symbols
=================

.. contents::
   :local:


.. _upload-basics:

Basics
======

Tecken lets you upload symbols. It stores these symbols files in an AWS S3
bucket allowing others to download them and symbolicate stacks against them.

When building products, you end up with a lot of symbols files that are very
large. Tecken upload requires you to package all the files into a ZIP file.
This both collects them and also compresses them.


Permissions and auth token
--------------------------

Uploading requires two things:

1. an account with upload permissions
2. an auth token for that account with upload permissions

The auth token is used in the HTTP POST to authenticate the upload.


Try symbols
-----------

Tecken differentiates "release builds" from "try builds".

Try builds can be kicked off by anyone and are typically used to debug or test
changes. There are many more Try builds than there are release builds. Try
builds tend to be more ephemeral and not very interesting after a week or two.

For this reason, Tecken lets you differentiate between "release builds" and
"try builds". Try build symbols won't override release build symbols. Try build
symbols files expire from our system after 28 days.

There are two ways to upload symbols for try builds:

1. Use an auth token with "Upload Try Symbols" permission.
2. Include ``try=1`` in the HTTP POST data.

Example with ``curl``:

.. code-block:: shell

    $ curl --user-agent "example/1.0" -X POST -H 'auth-token: xxx' \
        --form try=1 \
        --form myfile.zip=@myfile.zip \
        https://symbols.mozilla.org/upload/


See the :ref:`Try builds <download-try-builds>` documentation under **Download**.


Two ways to upload symbols
--------------------------

While there is one API endpoint, there are two different ways to upload
symbols.

1. Including the symbols ZIP file in the HTTP POST.

2. Uploading the ZIP file to a publicly available URL and then specifying
   that URL in the HTTP POST.


Upload by HTTP POST (payload < 2gb size)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Include the ZIP file in the HTTP POST to ``/upload/`` as a
``multipart/form-data`` payload.

Here's a ``curl`` example:

.. code-block:: shell

    $ curl --user-agent "example/1.0" -X POST -H 'auth-token: xxx' \
        --form myfile.zip=@myfile.zip \
        https://symbols.mozilla.org/upload/

Here's a Python example using the ``requests`` library:

.. code-block:: python

    >>> import requests
    >>> files = {"myfile.zip": open("path/to/myfile.zip", "rb")}
    >>> url = "https://symbols.mozilla.org/upload/"
    >>> headers = {"User-Agent": "example/1.0", "Auth-token": "xxx"}
    >>> response = requests.post(url, files=files, headers=headers)
    >>> response.status_code
    201

This works if the HTTP POST is less than 2gb. If the HTTP POST request is
larger than 2gb, then you'll need to use upload by download url.


Upload by download url (payload > 2gb size)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Upload the symbols file to some publicly available URL at an approved domain.

Then do an HTTP POST to ``/upload/`` as a ``application/x-www-form-urlencoded``
payload and specify the url to the symbols file as a value to ``url``.

Domains that Tecken will download from is specified in the
``DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS`` environment variable and at the
time of this writing is set to::

    queue.taskcluster.net
    public-artifacts.taskcluster.net

If you need another domain supported,
`file a bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General>`_.

Tecken will check redirects. At first a HEAD request is made with the URL and
Tecken will check both the original URL and the redirected URL against the list
of allowed URLs.

An example with ``curl``:

.. code-block:: shell

    $ curl --user-agent "example/1.0" -X POST -H 'auth-token: xxx' \
       -d url="https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip" \
       https://symbols.mozilla.org/upload/

An example with ``Python`` and the ``requests`` library:

.. code-block:: python

    >>> import requests
    >>> url = "https://symbols.mozilla.org/upload/"
    >>> headers = {"User-Agent": "example/1.0", "Auth-token": "xxx"}
    >>> data = {"url": "https://queue.taskcluster.net/YC0FgOlE/artifacts/symbols.zip"}
    >>> response = requests.post(url, data=data, headers=headers)
    >>> response.status_code
    201


Permissions and auth tokens
===========================

Uploading symbols to Tecken requires special permission. The process for
requesting access to upload symbols is roughly the following:

1. `Create a bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General>`_
   requesting access to upload symbols.

2. A Tecken admin will process the request.

   If you are a Mozilla employee, your manager will be needinfo'd to verify you need
   upload access.

   If you are not a Mozilla employee, we'll need to find someone to vouch for you.

3. After that's been worked out, the Tecken admin will give you permission to upload
   symbols.


Once you have permission to upload symbols, you will additionally need an auth
token. Once you log in, you can `create an API token
<https://symbols.mozilla.org/tokens>`_.  It needs to have the "Upload Symbols"
permission.


Upload: /upload/
================

.. http:post:: /upload/
   :synopsis: Upload symbols files.

   Upload symbols files as a ZIP file.

   :reqheader Content-Type: the content type of the payload

       * use ``multipart/form-data`` for Upload by HTTP POST
       * use ``application/x-www-form-urlencoded`` for Upload by Download URL

   :reqheader Auth-Token: the value of the auth token you're using

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :form <FILENAME>: the key is the name of the file and the value is the
       contents of the file; for example ``symbols.zip=<BINARY>``

       Use this for HTTP POST.

       Set this **or** ``url``--don't set both.

   :form url: the url for the symbols file

       Use this for Upload by Download URL

       Set this **or** ``<FILENAME>``--don't set both.

   :form try: use ``try=1`` if this is an upload of try symbols

   :statuscode 201: successful upload of symbols
   :statuscode 400: if the specified url can't be downloaded; verify that the url
       can be downloaded and retry
   :statuscode 403: your auth token is invalid and you need to get a new one
   :statuscode 413: your upload is too large; split it into smaller files or switch to
       upload by download url
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry


Symbols processing
==================

Tecken processes ZIP files in a couple of steps.

First, it validates the ZIP file. See section below on "Checks and Validation".

Once the ZIP file is validated, Tecken uploads the files in the ZIP file. For
files that are already in AWS S3, it skips the uploading step and just logs the
filename.

Records of the upload and what files were in it are available on the website.


Which S3 Bucket
===============

The S3 bucket that gets used for upload is based on a "default" and a map of
exceptions for certain users.

The default is configured as ``DJANGO_UPLOAD_DEFAULT_URL``. For example:
``https://s3-us-west-2.amazonaws.com/org-mozilla-symbols-public``.  From the
URL the bucket name is deduced and that's the default S3 bucket used.

The overriding is based on the **uploader's email address**. The default
configuration is to make no exceptions. But you can set
``DJANGO_UPLOAD_URL_EXCEPTIONS`` as a Python dict like this:

.. code-block:: shell

    $ export DJANGO_UPLOAD_URL_EXCEPTIONS={'*@adobe.com': 'https://s3.amazonaws.com/private-bucket'}


Checks and Validations
======================

First, Tecken checks the ZIP file to see if it's a valid ZIP file that contains
at least one file.

Then, Tecken iterates over the files in the ZIP file and checks if any file
contains the list of strings in ``settings.DISALLOWED_SYMBOLS_SNIPPETS``.  This
check is a block list check to make sure proprietary files are never uploaded
in S3 buckets that might be exposed publicly.

To override this amend the ``DJANGO_DISALLOWED_SYMBOLS_SNIPPETS`` environment
variable as a comma separated list. But be aware to include the existing
defaults which can be seen in ``settings.py``.

The final check is that each file path in the ZIP file matches the pattern
``<module>/<hex>/<file>`` or ``<name>-symbols.txt``. All other file paths are
ignored.


Gzip
====

Certain files get gzipped before being uploaded into S3. At the time of writing
that list is all ``.sym`` files. S3, unlike something like Nginx, doesn't do
content encoding on the fly based on the client's capabilities. Instead, we
manually gzip the file in memory in Tecken and set the additional
``ContentEncoding`` header to ``gzip``. Since these ``.sym`` files are always
text based, it saves a lot of memory in the S3 storage.

Additionally, the ``.sym`` files get their content type (aka. mime type) set
when uploading to S3 to ``text/plain``.  Because S3 can't know in advance that
the files are actually ASCII plain text, if you try to open them in a browser
it will set the ``Content-Type`` to ``application/octet-stream`` which makes it
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

A similar approach is done for files that *don't* need to be compressed.  In
the case of those files, we skip uploading, again, simply if the file size of
an existing file hasn't changed. However, that approach is too expensive for
compressed files. If we don't store and retrieve the original size and original
MD5 checksum, we have to locally compress the file to be able to make that
final size comparison. By instead checking the original size (and hash) we can
skip early without having to do the compression again.
