========
Glossary
========

.. glossary::
   :sorted:

   code file
   code_file
       The code file is the filename of the binary.

       For example, on Windows, the compiler may produce a ``.dll``
       file--that's the code file.

       This piece of data is only relevant for Windows binaries.


   code id
   code_id
   code identifier
   code_identifier
       The code id is generated when compiling a binary. It's 12 hex characters
       long.

       Example::

           6527E59F9071000


   debug file
   debug_file
       The debug file is the filename of the file that has debug information.

       For example, on Windows, the compiler may produce a ``.dll`` file and
       the debug file would be ``.pdb``.

       On Linux, the compiler may produce a ``.so`` file and the debug file
       would be the same.

       On MacOS, the compiler may produce a ``.dylib`` file and the debug file
       would be the same.


   debug id
   debug_id
   debug identifier
   debug_identifier
       The debug identifier is a string that identifies a specific build of a
       binary. Each build has a different debug identifier, so compiling the
       same binary twice in a row will yield two different debug identifiers.
       It is computed differently depending on the platform.

       Debug identifiers are 33 hexidecimal digits.

       Example::

           B7C0D76AF5EE3B644C4C44205044422E1

       Sometimes, it's shown hyphenated::

           b7c0d76a-f5ee-3b64-4c4c-44205044422e-1

       This debug identifier is the null debug identifier and it means we don't
       know what the debug identifier for the module is::

           000000000000000000000000000000000

       The debug identifier

       .. seealso::

          `Sentry docs on debug information <https://docs.sentry.io/platforms/native/guides/breakpad/data-management/debug-files/identifiers/>`__


   dump_syms
       dump_syms is a tool for parsing the debugging information the compiler
       provides (whether as DWARF or STABS sections in an ELF file or as
       stand-alone PDB files) and writing that information back out in the
       Breakpad symbol file format.

       .. seealso::

          `dump_syms <https://github.com/mozilla/dump_syms>`__
              dump_syms project.


   missing symbol
       Tecken stores symbols files for modules compiled by Mozilla build
       systems as well as system modules from device drivers, video drivers,
       system libraries, and other external things.

       When the Socorro processor processes a minidump, there are occasions
       when modules that Tecken does not have a symbols file for a module
       loaded in memory of the crashed process.

       We call this a "missing symbol".


   symbols
   symbols file
       When compiling a build, the compiler generates binaries with debugging
       symbols in them.

       The build system uses :term:`dump_syms` to extract the debugging symbols
       from the binaries and put them in Breakpad-style symbol files.

       An entry in the symbol file is something like "This set of bytes in this
       binary correspond to function JammyJamJam on line 200 in source file
       jampocalypso.c."

       Let's create a symbol file.

       We can create a new Rust project, build it, then extract symbols from
       it using :term:`dump_syms`::

           $ cargo new testproj
           $ cd testproj
           $ cargo build
           $ dump_syms target/debug/testproj > testproj.sym

       That creates a sym file like this::

           MODULE Linux x86_64 D48F191186D67E69DF025AD71FB91E1F0 testproj
           ...
           FILE 5 /home/willkg/projects/testproj/src/main.rs
           ...
           FUNC 5380 44 0 testproj::main
           5380 9 1 5
           5389 36 2 5
           53bf 5 3 5

       This sym file is 6,809 lines for a "Hello, world!" binary.

       .. seealso::

          `Breakpad symbol format <https://chromium.googlesource.com/breakpad/breakpad/+/HEAD/docs/symbol_files.md>`__
              Specification for Breakpad symbol file format.


   symbolication
       Symbolication is the act of converting an array of addresses and module
       information into symbols of the function in the source code for that
       address.

       Here's an array of modules loaded in memory and a stack defined as an
       array of memory offsets::

           {"jobs": [{
             "memoryMap": [
               [ "firefox.pdb", "5F84ACF1D63667F44C4C44205044422E1" ],
               [ "mozavcodec.pdb", "9A8AF7836EE6141F4C4C44205044422E1" ],
               [ "Windows.Media.pdb", "01B7C51B62E95FD9C8CD73A45B4446C71" ],
               [ "xul.pdb", "09F9D7ECF31F60E34C4C44205044422E1" ],
               // ...
             ],
             "stacks": [[
               [ 3, 6516407 ],
               [ 3, 12856365 ],
               [ 3, 12899916 ],
               [ 3, 13034426 ],
               [ 3, 13581214 ],
               [ 3, 13646510 ],
               // ...
             ]]
           }]}

       We can use the sym files, look up the memory addresses, and find the
       symbols for them. That gets us this::

           0  xul.pdb  mozilla::ConsoleReportCollector::FlushReportsToConsole(unsigned long long, nsIConsoleReportCollector::ReportAction)
           1  xul.pdb  mozilla::net::HttpBaseChannel::MaybeFlushConsoleReports()",
           2  xul.pdb  mozilla::net::HttpChannelChild::OnStopRequest(nsresult const&, mozilla::net::ResourceTimingStructArgs const&, mozilla::net::nsHttpHeaderArray const&, nsTArray<mozilla::net::ConsoleReportCollected> const&)
           3  xul.pdb  std::_Func_impl_no_alloc<`lambda at /builds/worker/checkouts/gecko/netwerk/protocol/http/HttpChannelChild.cpp:1001:11',void>::_Do_call()
          ...

       That's symbolication.

       .. seealso::

          `Mozilla Symbolication Server <https://symbolication.services.mozilla.com/>`__

          `Eliot <https://mozilla-eliot.readthedocs.io/>`__
              Documentation for the Mozilla Symbolication Server.
