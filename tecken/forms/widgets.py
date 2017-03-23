# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django import forms
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from .cache import CachedFileCache


class CachedFileHiddenInput(forms.HiddenInput):
    template_with_cachekey = """
<div class="alert alert-info">
    <span class="glyphicon glyphicon-exclamation-sign" aria-hidden="true"></span>
    <strong>Just uploaded file:</strong> %(file_name)s
    <p class="help-block">This file will be used when the form is successfully submitted</p>
</div>
%(cachekey_field)s
"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = CachedFileCache()

    def render(self, name, value, attrs=None):
        # render the hidden input first
        cachekey_field = super().render(name, value, attrs)

        # check if there is a cached file
        metadata = self.cache.metadata(value)
        if metadata is None:
            # if not, just return the hidden input
            return cachekey_field

        # or render the additional cached file
        return mark_safe(self.template_with_cachekey % {
            'file_name': conditional_escape(metadata['name']),
            'cachekey_field': cachekey_field,
        })
