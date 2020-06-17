=============
Symbolication
=============

.. contents::


Background
==========

Stacks
------

The stack is denoted as a list of lists. Each frame in the stack is composed
of two things:

1. the index in the modules list for the module for this frame
2. the memory offset relative to the base memory address for that module as
   an integer

For example, ``[1, 65802]`` is the 1-index module in the ``memoryMap`` and
module offset 65802.


Modules
-------

Modules are denoted by a debug filename and debug id. Without those, Tecken
can't find the symbols file for that module.

Each debug filename/debug id corresponds to a path in the symbols store. The
full URL comes from taking the base url, appending the debug filename,
appending the debug id, and then appending the debug filename with a ``.sym``
extensions.

For example, ``["wntdll.pdb", "D74F79EB1F8D4A45ABCD2F476CCABACC2"]`` becomes
``https://example.com/v1/wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym``.


Symbolication
-------------

Given a set of modules and a set of stacks, symbolication is the act of fetching
the debug symbols files for the modules, looking up the module offsets, and
then returning the symbol information.

For eaxmple, given this set of modules::

    [ "firefox.pdb", "5F84ACF1D63667F44C4C44205044422E1" ],
    [ "mozavcodec.pdb", "9A8AF7836EE6141F4C4C44205044422E1" ],
    [ "Windows.Media.pdb", "01B7C51B62E95FD9C8CD73A45B4446C71" ],
    [ "xul.pdb", "09F9D7ECF31F60E34C4C44205044422E1" ],
    ...

and this stack::

    [ 3, 6516407 ],
    [ 3, 12856365 ],
    [ 3, 12899916 ],
    [ 3, 13034426 ],
    ...

you might end up with something like this::

    0  xul.pdb  mozilla::ConsoleReportCollector::FlushReportsToConsole(unsigned long long, nsIConsoleReportCollector::ReportAction)
    1  xul.pdb  mozilla::net::HttpBaseChannel::MaybeFlushConsoleReports()",
    2  xul.pdb  mozilla::net::HttpChannelChild::OnStopRequest(nsresult const&, mozilla::net::ResourceTimingStructArgs const&, mozilla::net::nsHttpHeaderArray const&, nsTArray<mozilla::net::ConsoleReportCollected> const&)
    3  xul.pdb  std::_Func_impl_no_alloc<`lambda at /builds/worker/checkouts/gecko/netwerk/protocol/http/HttpChannelChild.cpp:1001:11',void>::_Do_call()
    ...


Symbolication: /symbolicate/v5
==============================

.. http:post:: /symbolicate/v5
   :synopsis: Symbolicates stacks.

   Symbolicate one or more stacks.

   Send an HTTP POST request with a JSON payload.

   **Example request:**

   .. sourcecode:: http

      POST /symbolicate/v5 HTTP/1.1

      {
        "jobs": [
          {
            "memoryMap": [
              [
                "xul.pdb",
                "44E4EC8C2F41492B9369D6B9A059577C2"
              ],
              [
                "wntdll.pdb",
                "D74F79EB1F8D4A45ABCD2F476CCABACC2"
              ]
            ],
            "stacks": [
              [
                [0, 11723767],
                [1, 65802]
              ]
            ]
          }
        ]
      }

   **Example response:**

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "results": [
          {
            "stacks": [
              [
                {
                  "frame": 0,
                  "module_offset": "0xb2e3f7",
                  "module": "xul.pdb",
                  "function": "sctp_send_initiate",
                  "function_offset": "0x4ca"
                },
                {
                  "frame": 1,
                  "module_offset": "0x1010a",
                  "module": "wntdll.pdb"
                }
              ]
            ],
            "found_modules": {
              "wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2": false,
              "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2": true
            }
          }
        ]
      }

   Here's an example you can copy and paste:

   .. code-block:: shell

       curl -d '{"jobs": [{"stacks":[[[0,11723767],[1, 65802]]],"memoryMap":[["xul.pdb","44E4EC8C2F41492B9369D6B9A059577C2"],["wntdll.pdb","D74F79EB1F8D4A45ABCD2F476CCABACC2"]]}]}' http://localhost:8000/symbolicate/v5


   **Tips:**

   1. Try to batch symbolication so a single request contains multiple jobs. That'll
      reduce the HTTP request/response overhead.
   2. If you get a non-200 response, wait a bit and try again.
   3. You should always get back a JSON response. If you don't, treat that like
      a failure, wait a bit and try again.
   4. If you're getting a 200 response, but some frames aren't symbolicated,
      then either Tecken doesn't have debugging symbols for that module or
      the debugging symbols for that module are malformed.

   :<json jobs: array of json objects each specifying a job
       to symbolicate

       :[].memoryMap: array of ``[debug name (str), debug id (str)]`` arrays

       :[].stacks: array of stacks where each stack is an array of
           ``[module index (int), memory offset (int)]`` arrays

   :>json results: array of result objects--one for every job

       :[].stacks: array of symbolicated stacks where each stack is an array
           of JSON objects

           :frame (int): frame index
           :module_offset (str): the module offset in hex
           :module (str): the module name
           :function (str): the function name
           :function_offset (str): the function offset in hex

       :[].found_modules: json object indicating which modules we had symbols
           for and which ones we didn't

           :<debug_filename>/<debug_id> (str): `true` if we found symbols, `false` if we didn't, and `null` if we
               didn't need to look up symbols because it's not referenced in the stacks


   :reqheader Debug: if you add ``Debug: true`` to the headers, then symbolication
       will also return debug information about cache lookups, how many downloads,
       timings, and some other things

   :statuscode 200: success symbolicating stacks
   :statuscode 500: something bad happened--please open up a bug
   :statuscode 503: problem downloading from symbols stores when symbolicating
       stacks; wait a bit and try again


Symbolication: /symbolicate/v4 (deprecated)
===========================================

.. http:post:: /symbolicate/v4
   :deprecated:
   :synopsis: Symbolicates stacks.

   Symbolicate one or more stacks.

   Send an HTTP POST request with a JSON payload.

   **Example request:**

   .. sourcecode:: http

      POST /symbolicate/v4 HTTP/1.1

      {
        "memoryMap": [
          [
            "xul.pdb",
            "44E4EC8C2F41492B9369D6B9A059577C2"
          ],
          [
            "wntdll.pdb",
            "D74F79EB1F8D4A45ABCD2F476CCABACC2"
          ]
        ],
        "stacks": [
          [
            [0, 11723767],
            [1, 65802]
          ]
        ],
        "version": 4
      }


   **Example response:**

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "symbolicatedStacks": [
          [
            "XREMain::XRE_mainRun() (in xul.pdb)",
            "KiUserCallbackDispatcher (in wntdll.pdb)"
          ]
        ],
        "knownModules": [
          true,
          true
        ]
      }
