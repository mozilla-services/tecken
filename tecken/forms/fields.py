# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django import forms


class CachedFileField(forms.FileField):
    """
    A custom FileField class for use in conjunction with CachedFileModelFormMixin
    that allows storing uploaded file in a cache for re-submission.

    That requires moving the "required" validation into the form's clean
    method instead of handling it on field level.
    """
    def __init__(self, *args, **kwargs):
        self.real_required = kwargs.pop('required', True)
        kwargs['required'] = False
        super().__init__(*args, **kwargs)
