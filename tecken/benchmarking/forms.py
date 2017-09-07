# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django import forms


class CachingVsBotoForm(forms.Form):
    iterations = forms.CharField(required=False)
    symbol_path = forms.CharField()

    def clean_iterations(self):
        try:
            value = int(self.cleaned_data['iterations'] or '10')
        except ValueError:
            raise forms.ValidationError('not an integer')
        if value <= 0:
            raise forms.ValidationError('must be >0')
        return value

    def clean_symbol_path(self):
        value = self.cleaned_data['symbol_path']
        if (
            not value.count('/') == 2 or
            value.startswith('/') or value.endswith('/')
        ):
            raise forms.ValidationError('Not valid')
        return value.strip()
