# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import re

from django.template.defaultfilters import filesizeformat as dj_filesizeformat


def filesizeformat(bytes):
    """the function django.template.defaultfilters.filesizeformat is
    nifty but it's meant for displaying in templates so it uses a
    whitespace-looking character instead of a space so it doesn't
    break in display. We don't need that here in this context."""
    return dj_filesizeformat(bytes).replace("\xa0", " ")


# Characters valid in the first and last part of a symbols file key. The allowed
# characters were originally based on what's valid in AWS S3 object keys:
#
# https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html
#
# While we are no longer using S3, and the requirements for GCS are a bit more relaxed,
# we currently don't have a use case for relaxing our requirements.
#
# https://cloud.google.com/storage/docs/objects#naming
#
# This is the list of "characters to avoid" from the S3 docs:
#
# * Backslash ("\")
# * Left curly brace ("{")
# * Non-printable ASCII characters (128–255 decimal characters)
# * Caret ("^")
# * Right curly brace ("}")
# * Percent character ("%")
# * Grave accent / back tick ("`")
# * Right square bracket ("]")
# * Quotation marks
# * 'Greater Than' symbol (">")
# * Left square bracket ("[")
# * 'Less Than' symbol ("<")
# * 'Pound' character ("#")
# * Vertical bar / pipe ("|")
#
# We also exlucde the slash character, since it separates the components of the key, so
# it can't occur within a component.
VALID_KEY_CHARS = r"[^\x00-\x1f\x80-\xff\\\^`><{}\[\]#%\"'\|/]+"

# The debug id in the key can only consist of hex characters.
VALID_HEX_CHARS = "[0-9A-Fa-f]+"

# A regular expression to validate a complete symbols file key.
VALID_KEY_REGEX = re.compile(
    f"""
    (?P<debug_name>{VALID_KEY_CHARS})
    /
    (?P<debug_id>{VALID_HEX_CHARS})
    /
    (?P<symbols_file>{VALID_KEY_CHARS})
    """,
    re.X,
)


def validate_key(key: str) -> bool:
    """Indicate whether the given key is valid.

    The key is matched against `VALID_KEY_REGEX`.
    """
    return bool(VALID_KEY_REGEX.fullmatch(key))
