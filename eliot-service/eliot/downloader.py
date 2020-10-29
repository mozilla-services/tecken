# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Contains code for downloading sym files from one or more sources.
"""

import markus

from eliot.librequests import session_with_retries
from eliot.libsentry import get_sentry_client


METRICS = markus.get_metrics(__name__)


class FileNotFound(Exception):
    """File was not found because it doesn't exist."""


class ErrorFileNotFound(Exception):
    """File was not found because of possible transient error."""


class Source:
    """Defines a source manager

    This takes a source url and then uses that to retrieve SYM files from the source.

    """

    def __init__(self, source_url):
        self.source_url = source_url

    def get(self, debug_filename, debug_id, filename):
        """Retrieve a source url.

        :arg str debug_filename: the debug_filename
        :arg str debug_id: the debug_id
        :arg str filename: the symbol filename

        :returns: bytes

        :raises FileNotFound: if the file cannot be found

        :raises ErrorFileNotFound: if the file cannot be found because of some possibly
            transient error like a timeout or a connection error

        """
        raise NotImplementedError


class HTTPSource(Source):
    """Source for HTTP/HTTPS requests."""

    def __init__(self, source_url):
        self.source_url = source_url.rstrip("/") + "/"
        self.session = session_with_retries()

    def _make_key(self, debug_filename, debug_id, filename):
        """Generates a key from given arguments

        :arg str debug_filename: the debug_filename
        :arg str debug_id: the debug_id
        :arg str filename: the symbol filename

        :returns: key as a str

        """
        # NOTE(willkg): This has to match Tecken's upload code
        return "%s/%s/%s" % (debug_filename, debug_id, filename)

    def get(self, debug_filename, debug_id, filename):
        """Retrieve a source url.

        :arg str debug_filename: the debug_filename
        :arg str debug_id: the debug_id
        :arg str filename: the symbol filename

        :returns: bytes

        :raises FileNotFound: if the file cannot be found

        :raises ErrorFileNotFound: if the file cannot be found because of some possibly
            transient error like a timeout or a connection error

        """
        key = self._make_key(debug_filename, debug_id, filename)
        url = "%s%s" % (self.source_url, key)

        resp = self.session.get(url, allow_redirects=True)
        if resp.status_code != 200:
            METRICS.incr("sym_download", tags=["statuscode:%d" % resp.status_code])

            # If the status_code is 404, that's a legitimate FileNotFound. Anything else
            # is either fishy or a server error.
            if resp.status_code == 404:
                raise FileNotFound("status_code: %s" % resp.status_code)

            # NOTE(willkg): This might be noisy, but we'll hone it as we get a better
            # feel for what "normal" and "abnormal" errors look like
            get_sentry_client().captureMessage(
                "error: symbol downloader got %s: %s"
                % (resp.status_code, resp.content[:100])
            )

            raise ErrorFileNotFound("status_code: %s" % resp.status_code)

        return resp.content


class SymbolFileDownloader:
    """Handles finding SYM files across one or more sources."""

    def __init__(self, source_urls):
        self.sources = []
        for source_url in source_urls:
            if source_url.startswith("http"):
                self.sources.append(HTTPSource(source_url))
            else:
                raise ValueError("No source for url: %s" % source_url)

    def get(self, debug_filename, debug_id, filename):
        """Retrieve a source url.

        :arg str debug_filename: the debug_filename
        :arg str debug_id: the debug_id
        :arg str filename: the symbol filename

        :returns: bytes

        :raises FileNotFound: if the file cannot be found

        :raises ErrorFileNotFound: if the file cannot be found because of some possibly
            transient error like a timeout or a connection error

        """
        errors = 0

        for source in self.sources:
            try:
                return source.get(debug_filename, debug_id, filename)
            except ErrorFileNotFound:
                errors += 1
            except FileNotFound:
                continue

        if errors:
            raise ErrorFileNotFound(
                "Error when retrieving file: %s %s %s"
                % (debug_filename, debug_id, filename)
            )
        else:
            raise FileNotFound(
                "File not found: %s %s %s" % (debug_filename, debug_id, filename)
            )
