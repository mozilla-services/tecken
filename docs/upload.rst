.. _upload:

=================
Uploading symbols
=================

.. contents::
   :local:


.. _upload-basics:

Basics
======

Tecken lets you upload :term:`symbols files <symbols file>`. It stores these
symbols files allowing others to use the download API to access them for
symbolicating stacks, profiling, debugging, etc.

When building software, you can run :term:`dump_syms` to extract debugging
information and generate symbols files.

You can upload your symbols ZIP file to Tecken using the upload API.


Symbols ZIP file structure
--------------------------

To upload symbols files, you must first put them in a ZIP file. The ZIP file
must consist of symbols files in this structure::

    <module>/<debug_id>/<file>

For example, here's the contents of a symbols ZIP file from a Firefox build::

    certutil/1AFC71D5AB0BEBD3C38BE53162EFA29A0/certutil.sym
    crashreporter/509BEAD7F29FDF02EC309704A35C48960/crashreporter.sym
    firefox-bin/4B736D100CA6655C9D41A138408EF4480/firefox-bin.sym
    firefox/F18AA48D06849232EE436621609EB9030/firefox.sym
    js/05817021DC072736D84A3D6F6800C09F0/js.sym
    libclearkey.so/6F805460FA945EDAC1FEB2229E7E5D310/libclearkey.so.sym
    libfakeopenh264.so/4E4B3E441ACA34CEC07655B61DBDCF880/libfakeopenh264.so.sym
    libfake.so/F50D7C64975965FD70357FF58DD0615C0/libfake.so.sym
    libfreebl3.so/D23A341A8B2614640D094F0CC429A8A80/libfreebl3.so.sym
    libfreeblpriv3.so/3D7CE9A569ED46B0C77DBD3A4B1EA0470/libfreeblpriv3.so.sym
    libipcclientcerts.so/8C9A9FCF80F9CE0797E7746FF900765F0/libipcclientcerts.so.sym
    liblgpllibs.so/80AE7BD11E2532CFFC217154968DA6A00/liblgpllibs.so.sym
    libmozavcodec.so/555BF9F90CE583DF21FB525B7E6243FF0/libmozavcodec.so.sym
    libmozavutil.so/57AC5DFA71D0C5880517CF195A69A1860/libmozavutil.so.sym
    libmozgtk.so/21FB2BB8FD80120D6C131AFE2EC88A080/libmozgtk.so.sym
    libmozsandbox.so/CBBC8F7B7794A777E2F7BCAD64EE03780/libmozsandbox.so.sym
    libmozsqlite3.so/F913FF352E918F683FAF4FAD5C0182BD0/libmozsqlite3.so.sym
    libmozwayland.so/2226E0AEA0C87E748BA72A6BF258F3550/libmozwayland.so.sym
    libnspr4.so/13530EC7CAB3F71EE091E41721F13CC30/libnspr4.so.sym
    libnss3.so/9D8322087BEBED332EAEED0F5D6975870/libnss3.so.sym
    libnssckbi.so/163C00046AA9E6198B61A6045C38E3650/libnssckbi.so.sym
    libnssutil3.so/6A9E332D4559D83FFF6C725DCB7A98870/libnssutil3.so.sym
    libplc4.so/BCD4DD0CF3614CB57D4AD189633B820F0/libplc4.so.sym
    libplds4.so/58120BEB46A8D9B05C89DF8124D753400/libplds4.so.sym
    libsmime3.so/E0897F4BD6626CE490F4974A5494B7000/libsmime3.so.sym
    libsoftokn3.so/C01F5710501A0528AC50D472C754254E0/libsoftokn3.so.sym
    libssl3.so/84283CDA8EBD0F78E6118BC869E6DE150/libssl3.so.sym
    libxul.so/5C63DDEA1326BB8DADFCC7D606633D1E0/libxul.so.sym
    logalloc-replay/DA0BFC167FB27B4A50763355964523DE0/logalloc-replay.sym
    minidump-analyzer/9F3842DFF1F104156D658A5E4493539F0/minidump-analyzer.sym
    modutil/847194C9942BB8D079E43A1D8FD077280/modutil.sym
    pingsender/6129FD5C877F2C22EAC832C26678E8A40/pingsender.sym
    pk12util/C119F9093FCBD813277074CBCD35154B0/pk12util.sym
    plugin-container/45A20FE024EAD3B49CDF292851C2DD4B0/plugin-container.sym
    shlibsign/835151A0E5F29FF71AD93C37F0C1E30A0/shlibsign.sym
    signmar/53F4637B906F2E00353A8B451A754B7A0/signmar.sym
    updater/3D7533ED47669F8A207B93E4512C35870/updater.sym
    xpcshell/B95F899A59E247055C0ED7883D0235A40/xpcshell.sym


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


Upload by HTTP POST
~~~~~~~~~~~~~~~~~~~

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


.. Note::

   If the HTTP POST payload is > 1.5gb, we suggest splitting the symbols up
   across multiple HTTP POST requests.

   The system has a maximum payload size of 2gb.

   The larger the payload, the longer it takes to process and the more likely
   that the HTTP POST fails.

   If an HTTP POST fails, whatever work that was finished sticks--future
   attempts will skip redoing that work.


Upload by download url
~~~~~~~~~~~~~~~~~~~~~~

If your symbols zip archive is already available at a publicly available URL at
an approved domain, then you can do an upload-by-download where the payload of
the HTTP POST is a url to the symbols zip archive.

Do an HTTP POST to ``/upload/`` as a ``application/x-www-form-urlencoded``
payload and specify the url to the symbols file as a value to ``url``.

Domains that Tecken will download from is specified in the
``DJANGO_ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS`` environment variable and at the
time of this writing is set to::

    queue.taskcluster.net
    firefox-ci-tc.services.mozilla.com


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


.. Note::

   If the HTTP POST payload is > 1.5gb, we suggest splitting the symbols up
   across multiple HTTP POST requests.

   The system has a maximum payload size of 2gb.

   The larger the payload, the longer it takes to process and the more likely
   that the HTTP POST fails.

   If an HTTP POST fails, whatever work that was finished sticks--future
   attempts will skip redoing that work.


Permissions and auth tokens
===========================

:production:     https://symbols.mozilla.org/
:create a bug:   https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General
:create a token: https://symbols.mozilla.org/tokens

Uploading symbols to Tecken requires special permission. The process for
requesting access to upload symbols is roughly the following:

1. Log into `Mozilla Symbols Server <https://symbols.mozilla.org/>`__. When you
   log in, an account will be created automatically.

2. `Create a bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General>`_
   requesting access to upload symbols.

3. A Tecken admin will process the request.

   If you are a Mozilla employee, your manager will be needinfo'd to verify you need
   upload access.

   If you are not a Mozilla employee, we'll need to find someone to vouch for you.

4. After that's been worked out, the Tecken admin will give you permission to upload
   symbols.

Once you have permission to upload symbols, you will additionally need an auth
token. Once you log in, you can `create an API token
<https://symbols.mozilla.org/tokens>`__.  It needs to have the "Upload Symbols"
or "Upload Try Symbols" permission.

The auth token is sent as an ``Auth-Token`` HTTP header in the HTTP POST.

.. Note::

   Auth tokens support labels to make it easier to know which auth token has
   which permissions. A `-` and anything after that in the auth token is
   considered a label and ignored.

   For example, if you had an auth token for "Upload Try Symbols"::

      E468C3D4BBDA43DEBC0B856983895835

   you could use::

      E468C3D4BBDA43DEBC0B856983895835-uploadtry-20230913


Testing symbol uploads with our stage environment
=================================================

:stage:          https://symbols.stage.mozaws.net/
:create a token: https://symbols.stage.mozaws.net/tokens

If you're testing symbol uploads out, testing something that uses symbol files,
testing a symbol upload script, or something like that, you might want to use
our *staging* server. Then the tests you're doing won't affect production and
potentially everyone using production.

To get access to our stage server:

1. Log into `Mozilla Symbols Server (stage)
   <https://symbols.stage.mozaws.net/>`__. When you log in, an account will be
   created automatically.

2. Ask a Tecken admin to grant you upload permissions.

   We hang out in `#crashreporting matrix channel
   <https://chat.mozilla.org/#/room/#crashreporting:mozilla.org>`_.

   You can also find us on Slack or send us an email--whatever works best for
   you.

Once you have permission to upload symbols, you will additionally need an auth
token. Once you log in, you can `create an API token
<https://symbols.stage.mozaws.net/tokens>`__.  It needs to have the "Upload
Symbols" or "Upload Try Symbols" permission.

The auth token is sent as an ``Auth-Token`` HTTP header in the HTTP POST.

.. Note::

   Auth tokens created in production won't work on stage and auth tokens
   created on stage won't work in production.


Improving symbol upload success rate
====================================

Tecken tries to do as much as it can when handling the symbol upload request.
Subsequent attempts will pick up where they left off--files that have been
processed won't be reprocessed.

If you find your symbols upload job is getting HTTP 429 or 5xx responses often
or it doesn't seem like symbol uploads are being completed, try these tips:

1. break up the zip file into smaller zip files to upload
2. increase the amount of time you're giving to uploading symbols, increase the
   number of retry attempts, and increase the time between retry attempts
3. change the time of day that you're doing symbol uploads


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
   :statuscode 429: your request has been rate-limited; sleep for a bit and retry
   :statuscode 500: there's an error with the server; sleep for a bit and
       retry; if retrying doesn't work, then please file a bug report
   :statuscode 502: sleep for a bit and retry
   :statuscode 503: sleep for a bit and retry
   :statuscode 504: the request is taking too long to complete; sleep for a bit
       and retry


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

The S3 bucket for symbols is configured by ``DJANGO_UPLOAD_DEFAULT_URL``. For
example: ``https://s3-us-west-2.amazonaws.com/org-mozilla-symbols-public``.
From the URL the bucket name is deduced and that's the default S3 bucket used.


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

The final check is to make sure that each file in the ZIP file is either:

1. ``<module>/<debug_id>/<file>`` for symbols files.

   Example::

       firefox/F18AA48D06849232EE436621609EB9030/firefox.sym

2. ``<name>-symbols.txt`` for file listings relative to the root of the zip
   file.

   While these files can exist in your ZIP file, they're silently ignored.


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
