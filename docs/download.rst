.. _download:

========
Download
========

.. contents::
   :local:

Basics
======

The Tecken webapp handles download requests for
:term:`symbols files <symbols file>`. Tecken handles download API requests,
determines whether the symbols file exists and which storage location it's in,
and returns a redirect to the storage location. In this way, we can store
symbols files in multiple places and there's a single place to request them.

For example, at the time of this writing doing a ``GET`` for
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym` will
return a ``302 Found`` redirect to the file in storage.


.. _download-try-builds:

Try Builds
==========

Try builds are ephemeral and we store the symbols from those builds for shorter
period of time than we store symbols from regular builds. Generally, try builds
are only useful in cases where engineers are debugging specific crashes in the
code they're working on. For this reason, by default, Tecken does not look
for symbols files in storage locations for try build symbols files.

If you want to download symbols files for regular and try builds, you have to
specify that in the download API request. There are two ways to do it:

1. use the ``/try`` prefix

   Example::

       https://symbols.mozilla.org/try/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym
                                  ^^^^

   This is helpful if you're using a debugger. You can set the symbols server
   to::

       https://symbols.mozilla.org/try

   and pick up regular and try build symbols files.

2. use the ``try`` query string parameter

   Example::

       https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym?try=1
                                                                                            ^^^^^^

When you do either of these, Tecken will look for symbols files in storage
locations for both regular and try build symbols files with a preference for
regular build symbols files first.


Downloading API
===============

.. http:head:: /(str:debug_filename)/(hex:debug_id)/(str:symbol_file)
               /try/(str:debug_filename)/(hex:debug_id)/(str:symbol_file)

   Determine whether the symbol file exists or not.

   For finding regular and try symbols files, either prefix the path with
   ``/try`` or include ``try=1`` querystring parameter.

   Example request:

   .. sourcecode:: http

      HEAD /xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      Host: symbols.mozilla.org
      User-Agent: example/1.0

   .. sourcecode:: http

      HEAD /try/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      Host: symbols.mozilla.org
      User-Agent: example/1.0

   :param str debug_filename: the filename of the debug file

   :param hex debug_id: the debug id in hex characters all upper-cased

   :param str symbol_file: the filename of the symbol file; ends with ``.sym``

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is ``0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download regular and try build symbols files
       with a preference for regular build symbols files

   :query _refresh: use ``_refresh=1`` to force Tecken to update cache

   :statuscode 200: symbol file exists
   :statuscode 404: symbol file does not exist
   :statuscode 429: your request has been rate-limited; sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 502: sleep for a bit and retry
   :statuscode 503: sleep for a bit and retry
   :statuscode 504: sleep for a bit and retry


.. http:get:: /(str:debug_filename)/(hex:debug_id)/(str:symbol_file)
              /try/(str:debug_filename)/(hex:debug_id)/(str:symbol_file)

   Download a symbol file.

   For finding regular and try symbols files, either prefix the path with
   ``/try`` or include ``try=1`` querystring parameter.

   Example request:

   .. sourcecode:: http

      GET /xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      Host: symbols.mozilla.org
      User-Agent: example/1.0

   Example curl::

      $ curl --location --user-agent "example/1.0" --verbose \
          https://symbols.mozilla.org/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym
      > GET /xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: example/1.0
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Date: Tue, 24 Oct 2023 17:56:33 GMT
      < Location: https://s3.us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /org.mozilla.crash-stats.symbols-public/v1/xul.pdb/B7DC60E91588D8A54C4C44205044422E1/xul.sym HTTP/1.1
      > Host: s3.us-west-2.amazonaws.com
      > User-Agent: example/1.0
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

   :param str debug_filename: the filename of the debug file

   :param hex debug_id: the debug id in hex characters all upper-cased

   :param str symbol_file: the filename of the symbol file; ends with ``.sym``

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is ``0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download regular and try build symbols files
       with a preference for regular build symbols files

   :query _refresh: use ``_refresh=1`` to force Tecken to update cache

   :resheader Location: redirect location for the file; see :http:get:`SYMBOLFILE`.

   :statuscode 302: symbol file was found--follow redirect url in ``Location`` header in
       the response to get to the final url
   :statuscode 400: param values have bad characters in them or are otherwise invalid
   :statuscode 404: symbol file was not found
   :statuscode 429: your request has been rate-limited; sleep for a bit and retry
   :statuscode 500: there's an error with the server; sleep for a bit and
       retry; if retrying doesn't work, then please file a bug report
   :statuscode 502: sleep for a bit and retry
   :statuscode 503: sleep for a bit and retry
   :statuscode 504: sleep for a bit and retry


.. http:get:: /(str:code_filename)/(hex:code_id)/(str:symbol_file)
              /try/(str:code_filename)/(hex:code_id)/(str:symbol_file)

   Same as :http:get:`/(str:debug_filename)/(hex:debug_id)/(str:symbol_file)`,
   but this will look up the debug filename and debug id for a module using the
   code filename and code id and return a redirect to the download API with the
   debug filename and debug id.

   For finding regular and try symbols files, either prefix the path with
   ``/try`` or include ``try=1`` querystring parameter.

   .. Note::

      This is only helpful for symbols files for modules compiled for Windows.
      Modules compiled for other operating systems don't have code files and
      code ids.

   Example request:

   .. sourcecode:: http

      GET /xul.dll/652DE0ED706D000/xul.sym HTTP/1.1
      Host: symbols.mozilla.org
      User-Agent: example/1.0

   .. sourcecode:: http

      GET /try/xul.dll/652DE0ED706D000/xul.sym HTTP/1.1
      Host: symbols.mozilla.org
      User-Agent: example/1.0

   Example curl::

      $ curl --location --user-agent "example/1.0" --verbose \
          https://symbols.mozilla.org/xul.dll/652DE0ED706D000/xul.sym
      > GET /xul.dll/652DE0ED706D000/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: example/1.0
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Date: Tue, 24 Oct 2023 17:49:08 GMT
      < Location: /xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym HTTP/1.1
      > Host: symbols.mozilla.org
      > User-Agent: example/1.0
      > Accept: */*
      >
      < HTTP/1.1 302 Found
      < Location: https://s3.us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym
      < Content-Length: 0

      > GET /org.mozilla.crash-stats.symbols-public/v1/xul.pdb/569E0A6C6B88C1564C4C44205044422E1/xul.sym HTTP/1.1
      > Host: s3.us-west-2.amazonaws.com
      > User-Agent: example/1.0
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

   :param str code_filename: the filename of the code file

   :param hex code_id: the code id in hex characters all upper-cased

   :param str symbol_file: the filename of the symbol file; ends with ``.sym``


.. http:get:: SYMBOLFILE

   This covers the download API response ``Location`` value url redirect.

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :resheader Content-Length: length of the response body; if the body is
       compressed, it's the size of the compressed body
   :resheader Content-Type: content type of the response after decompressing
       it; will be text/plain for symbol files
   :resheader Content-Encoding: (optional) set to ``gzip`` if the object is
       gzip-compressed; note that ``.sym`` files are compressed even though the
       file extension doesn't indicate that

   :statuscode 404: symbol file was not found
   :statuscode 500: there's an error with the server; sleep for a bit and
       retry; if retrying doesn't work, then please file a bug report
   :statuscode 502: sleep for a bit and retry
   :statuscode 503: sleep for a bit and retry
   :statuscode 504: sleep for a bit and retry
