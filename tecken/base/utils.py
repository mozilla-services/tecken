# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from django.template.defaultfilters import filesizeformat as dj_filesizeformat


def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
):
    """Opinionated wrapper that creates a requests session with a
    HTTPAdapter that sets up a Retry policy that includes connection
    retries.

    If you do the more naive retry by simply setting a number. E.g.::

        adapter = HTTPAdapter(max_retries=3)

    then it will raise immediately on any connection errors.
    Retrying on connection errors guards better on unpredictable networks.
    From http://docs.python-requests.org/en/master/api/?highlight=retries#requests.adapters.HTTPAdapter
    it says: "By default, Requests does not retry failed connections."

    The backoff_factor is documented here:
    https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.retry.Retry
    A default of retries=3 and backoff_factor=0.3 means it will sleep like::

        [0.3, 0.6, 1.2]
    """  # noqa
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def filesizeformat(bytes):
    """the function django.template.defaultfilters.filesizeformat is
    nifty but it's meant for displaying in templates so it uses a
    whitespace-looking character instead of a space so it doesn't
    break in display. We don't need that here in this context."""
    return dj_filesizeformat(bytes).replace('\xa0', ' ')


# See the docstring in invalid_s3_key_name_characters for an explanation
# of this regex.
INVALID_S3_CHARS_REGEX = re.compile(
    # \x00-\x1f is the "ASCII control characters". That's 00 (Null character)
    # until 31 (Unit separator) (whatever that is).
    r'[\x00-\x1f\x80-\xff\\\^`><{}\[\]#%"\'\~\|]'
)


def invalid_s3_key_name_characters(key):
    """Return true if there are characters in the key name that is
    considered invalid.
    Invalid is based on the official S3 documentation.
    https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html

    In particular, they list a set of "Characters to Avoid". They are
    as follows:

        * Backslash ("\")
        * Left curly brace ("{")
        * Non-printable ASCII characters (128–255 decimal characters)
        * Caret ("^")
        * Right curly brace ("}")
        * Percent character ("%")
        * Grave accent / back tick ("`")
        * Right square bracket ("]")
        * Quotation marks
        * 'Greater Than' symbol (">")
        * Left square bracket ("[")
        * Tilde ("~")
        * 'Less Than' symbol ("<")
        * 'Pound' character ("#")
        * Vertical bar / pipe ("|")

    This function can be used also to avoid or outright refuse to bother
    looking up if we have a symbol. This is useful in the Download part
    where we don't want clients to be able to try to break the underlying
    XML API by attempting lookups on really "strange" control characters.
    E.g. https://bugzilla.mozilla.org/show_bug.cgi?id=1427730

    Because this function gets used a lot, by the Download view functions,
    it's important that this function is as fast as it can be. Therefore,
    consider the following pre-optimization observations:

        * Doing `invalid_s3_key_name_characters('foo.pdb' + hex + 'foo.sym')`
          is 25% slower than doing
          `invalid_s3_key_name_characters('foo.pdb'  'foo.sym')`.
          I.e. the fewer characters to check, the faster. The debug ID
          can be checked differently.

        * There is no significant performance difference between using
          regex.findall() and regex.search(). But surprisingly, looping
          and exiting as early as possible with regex.finditer() is
          about 25% slower.

        * Since the key is usually made up of a symbol +/+ debugid +/+ filename
          you might be tempted to do `(invalid_s3_key_name_characters(symbol)
          OR invalid_s3_key_name_characters(filename))` but this is
          empirically slower than making a new string like this:
          `invalid_s3_key_name_characters(symbol + filename)`.

          Also, doing `''.join([symbol, filename])` is actually 15% slower
          than just adding two strings with `symbol + filename`.

    Note! It is valid to have Emojis or other Unicode characters (that
    aren't part of the "Extended ASCCI Characters"). For example,
    `cookié` is not valid, but `🍪` is valid. This might seem odd but
    it's entirely based on the above mentioned official S3 documentation.
    """
    return bool(INVALID_S3_CHARS_REGEX.findall(key))
