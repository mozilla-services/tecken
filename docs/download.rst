.. _download:

========
Download
========

.. contents::
   :local:

Basics
======

The Tecken webapp handles requests for :term:`symbols files <symbols file>`.
Tecken takes the request, figures out which bucket the file is in, and returns
a redirect to that bucket. This allows us to use multiple buckets for symbols
without requiring everyone to maintain lists of buckets.

For example, at the time of this writing doing a ``GET`` for
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym` will
return a ``302 Found`` redirect to the file in storage.


.. _download-try-builds:

Try Builds
==========

By default, when you request to download a symbol, Tecken will iterate through
a list of available S3 configurations.

To download symbols that might be part of a Try build you have to pass an
optional query string key ``try`` or you can prefix the URL with ``/try``.
For example:

.. code-block:: shell

    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/tried.pdb/HEX/tried.sym?try
    ...302 Found...

    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/try/tried.pdb/HEX/tried.sym
    ...302 Found...

If you specify that you're requesting a Try build, Tecken will look at
all the S3 bucket locations as well as all the Try locations in those
S3 buckets.

Symbols from Try builds is always tried last! So if there's a known symbol
called ``foo.pdb/HEX/foo.sym`` and someone triggers a Try build (which uploads
its symbols) with the exact same name (and build ID) and even if you use
``https://symbols.mozilla.org/foo.pdb/HEX/foo.sym?try`` the existing (non-Try
build) symbol will be matched first.


Downloading API
===============

.. http:head:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Determine whether the symbol file exists or not.

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is `0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force Tecken to update cache

   :statuscode 200: symbol file exists
   :statuscode 404: symbol file does not exist
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry


.. http:head:: /try/<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Same as ``HEAD /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but this will
   check try symbols and then regular symbols.


.. http:get:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Download a symbol file.

   Example::

      $ curl -L --verbose https://symbols.mozilla.org/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym
      > GET /xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: curl/7.88.1
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Date: Tue, 24 Oct 2023 17:56:33 GMT
      < Location: https://s3.us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /org.mozilla.crash-stats.symbols-public/v1/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      > Host: s3.us-west-2.amazonaws.com
      > User-Agent: curl/7.88.1
      > Accept: */*
      >
      < HTTP/1.1 200 OK
      < Date: Tue, 24 Oct 2023 17:56:35 GMT
      < ETag: "e2e35ff973763bcda524f147981008bc"
      < Content-Encoding: gzip
      < Content-Type: text/plain
      < Content-Length: 143395908
      <
      <OUTPUT>

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is `0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force Tecken to update cache

   :statuscode 302: symbol file was found--follow redirect url in ``Location`` header in
       the response to get to the final url
   :statuscode 400: requested symbol file has bad characters
   :statuscode 404: symbol file was not found
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report


.. http:get:: /<CODE_FILENAME>/<CODE_ID>/<SYMBOL_FILE>

   Same as ``GET /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but this will
   look up the debug filename and debug id for a module using the code filename
   and code id and return a redirect to the download API with the debug
   filename and debug id.

   Example::

      $ curl -L --verbose https://symbols.mozilla.org/xul.dll/652DE0ED706D000/xul.sym
      > GET /xul.dll/652DE0ED706D000/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: curl/7.88.1
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Date: Tue, 24 Oct 2023 17:49:08 GMT
      < Location: /xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: curl/7.88.1
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Location: https://s3.us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /org.mozilla.crash-stats.symbols-public/v1/xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym HTTP/1.1
      > Host: s3.us-west-2.amazonaws.com
      > User-Agent: curl/7.88.1
      > Accept: */*
      >
      < HTTP/1.1 200 OK
      < Date: Tue, 24 Oct 2023 17:49:09 GMT
      < ETag: "da6d99617b2c9b1e58166f0b93bcb0ac"
      < Content-Encoding: gzip
      < Content-Type: text/plain
      < Content-Length: 108311752
      <
      <OUTPUT>

.. http:get:: /try/<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Same as ``GET /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but this will
   check try symbols and then regular symbols

.. http:get:: /try/<CODE_FILENAME>/<CODE_ID>/<SYMBOL_FILE>

   Same as ``GET /try/<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but this
   will look up the debug filename and debug id for a module using the code
   filename and code id.
