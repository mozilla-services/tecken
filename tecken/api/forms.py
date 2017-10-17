# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import re

import dateutil

from django import forms
from django.contrib.auth.models import Permission, Group, User
from django.utils import timezone


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


class TokensForm(forms.Form):
    state = forms.CharField(required=False)

    def clean_state(self):
        value = self.cleaned_data['state']
        if value and value not in ('expired', 'all'):
            raise forms.ValidationError(
                f'Unrecognized state value {value!r}'
            )
        return value


class UserEditForm(forms.ModelForm):

    groups = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ('is_active', 'is_superuser')

    def clean_groups(self):
        value = self.cleaned_data['groups']
        groups = []
        for pk in [x for x in value.split(',') if x.strip()]:
            try:
                groups.append(Group.objects.get(id=pk))
            except ValueError:
                raise forms.ValidationError('Invalid group ID')
        return groups


class PaginationForm(forms.Form):
    page = forms.CharField(required=False)

    def clean_page(self):
        value = self.cleaned_data['page']
        try:
            value = int(value or 1)
        except ValueError:
            raise forms.ValidationError(f'Not a number {value!r}')
        if value < 1:
            value = 1
        return value


class BaseFilteringForm(forms.Form):

    def _clean_dates(self, values):
        """return a list of either a datetime, date or None.
        Each one can have an operator."""
        if not values:
            return []
        dates = []
        operators = re.compile('<=|>=|<|>|=')
        for block in [x.strip() for x in values.split(',') if x.strip()]:
            if operators.findall(block):
                operator, = operators.findall(block)
            else:
                operator = '='
            rest = operators.sub('', block).strip()
            if rest.lower() in ('null', 'incomplete'):
                date_obj = None
            elif rest.lower() == 'today':
                date_obj = timezone.now().replace(hour=0, minute=0, second=0)
            elif rest.lower() == 'yesterday':
                date_obj = timezone.now().replace(hour=0, minute=0, second=0)
                date_obj -= datetime.timedelta(days=1)
            else:
                try:
                    date_obj = dateutil.parser.parse(rest)
                except ValueError:
                    raise forms.ValidationError(f'Unable to parse {rest!r}')
                if timezone.is_naive(date_obj):
                    date_obj = timezone.make_aware(date_obj)
            dates.append((operator, date_obj))

        return dates


class UploadsForm(BaseFilteringForm):
    user = forms.CharField(required=False)
    size = forms.CharField(required=False)
    created_at = forms.CharField(required=False)
    completed_at = forms.CharField(required=False)

    def clean_user(self):
        value = self.cleaned_data['user']
        operator = '='  # default
        if value.startswith('!'):
            operator = '!'
            value = value[1:].strip()
        if value:
            try:
                return [operator, User.objects.get(email__iexact=value)]
            except User.DoesNotExist:
                try:
                    return [operator, User.objects.get(email__icontains=value)]
                except User.DoesNotExist:
                    raise forms.ValidationError('User not found')
                except User.MultipleObjectsReturned:
                    raise forms.ValidationError('User search ambiguous')

    def clean_size(self):
        values = self.cleaned_data['size']
        if not values:
            return []
        sizes = []
        operators = re.compile('<=|>=|<|>|=')
        multipliers = re.compile('gb|mb|kb|g|m|k|b', re.I)
        multiplier_aliases = {
            'gb': 1024 * 1024 * 1024,
            'g': 1024 * 1024 * 1024,
            'mb': 1024 * 1024,
            'm': 1024 * 1024,
            'kb': 1024,
            'k': 1024,
            'b': 1,
        }
        for block in [x.strip() for x in values.split(',') if x.strip()]:
            if operators.findall(block):
                operator, = operators.findall(block)
            else:
                operator = '='
            rest = operators.sub('', block)
            if multipliers.findall(rest):
                multiplier, = multipliers.findall(rest)
            else:
                multiplier = 'b'
            rest = multipliers.sub('', rest)
            try:
                rest = float(rest)
            except ValueError:
                raise forms.ValidationError(f'{rest!r} is not numeric')
            rest = multiplier_aliases[multiplier.lower()] * rest
            sizes.append((operator, rest))
        return sizes

    def clean_created_at(self):
        return self._clean_dates(self.cleaned_data['created_at'])

    def clean_completed_at(self):
        return self._clean_dates(self.cleaned_data['completed_at'])


class FileUploadsForm(UploadsForm):
    size = forms.CharField(required=False)
    created_at = forms.CharField(required=False)
    completed_at = forms.CharField(required=False)
    key = forms.CharField(required=False)
    download = forms.CharField(required=False)
    update = forms.BooleanField(required=False)
    compressed = forms.BooleanField(required=False)
    bucket_name = forms.CharField(required=False)

    def clean_key(self):
        values = self.cleaned_data['key']
        if not values:
            return []
        return [x.strip() for x in values.split(',') if x.strip()]

    def clean_download(self):
        value = self.cleaned_data['download']
        if value:
            if value not in ('microsoft',):
                raise forms.ValidationError(
                    f'Unrecognized download value {value!r}'
                )
        return value

    def clean_bucket_name(self):
        values = self.cleaned_data['bucket_name']
        if not values:
            return []
        cleaned = []
        for value in values.split(','):
            if value.strip():
                if value.startswith('!'):
                    operator = '!'
                    value = value[1:].strip()
                else:
                    operator = '='
                cleaned.append((operator, value))
        return cleaned


class DownloadsMissingForm(BaseFilteringForm):
    symbol = forms.CharField(required=False)
    debugid = forms.CharField(required=False)
    filename = forms.CharField(required=False)
    code_file = forms.CharField(required=False)
    code_id = forms.CharField(required=False)
    modified_at = forms.CharField(required=False)
    count = forms.CharField(required=False)

    def clean_modified_at(self):
        return self._clean_dates(self.cleaned_data['modified_at'])

    def clean_count(self):
        values = self.cleaned_data['count']
        if not values:
            return []
        operators = re.compile('<=|>=|<|>|=')
        counts = []
        for block in [x.strip() for x in values.split(',') if x.strip()]:
            if operators.findall(values):
                operator, = operators.findall(block)
            else:
                operator = '='
            rest = operators.sub('', block)
            try:
                rest = int(rest)
            except ValueError:
                raise forms.ValidationError(f'{rest!r} is not a number')
            counts.append((operator, rest))
        return counts


class DownloadsMicrosoftForm(DownloadsMissingForm):
    created_at = forms.CharField(required=False)
    state = forms.CharField(required=False)
    error = forms.CharField(required=False)

    def clean_created_at(self):
        return self._clean_dates(self.cleaned_data['created_at'])
