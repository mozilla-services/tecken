# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User


class TokenForm(forms.Form):
    permissions = forms.CharField()
    notes = forms.CharField(required=False)
    expires = forms.CharField()

    def clean_expires(self):
        value = self.cleaned_data['expires']
        try:
            return int(value)
        except ValueError:
            raise forms.ValidationError(
                f'Invalid number of days ({value!r})'
            )

    def clean_permissions(self):
        value = self.cleaned_data['permissions']
        permissions = []
        for pk in value.split(','):
            permissions.append(
                Permission.objects.get(id=pk)
            )
        return permissions


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('is_active', 'is_superuser', 'groups')
