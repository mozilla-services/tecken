# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import re

import dateutil

from django import forms
from django.utils import timezone


class PaginationForm(forms.Form):
    page = forms.CharField(required=False)

    def clean_page(self):
        value = self.cleaned_data["page"]
        try:
            value = int(value or 1)
        except ValueError:
            raise forms.ValidationError(f"Not a number {value!r}")
        if value < 1:
            value = 1
        return value


class DownloadForm(forms.Form):
    code_file = forms.CharField(required=False)
    code_id = forms.CharField(required=False)


class DownloadsMissingForm(forms.Form):
    symbol = forms.CharField(required=False)
    debugid = forms.CharField(required=False)
    filename = forms.CharField(required=False)
    code_file = forms.CharField(required=False)
    code_id = forms.CharField(required=False)
    modified_at = forms.CharField(required=False)
    sort = forms.CharField(required=False)
    reverse = forms.CharField(required=False)

    def _clean_dates(self, values):
        """Return a list of either a date or None.

        Each one can have an operator.

        """
        if not values:
            return []
        dates = []
        operators = re.compile("<=|>=|<|>|=")
        for block in [x.strip() for x in values.split(",") if x.strip()]:
            if operators.findall(block):
                (operator,) = operators.findall(block)
            else:
                operator = "="
            rest = operators.sub("", block).strip()
            if rest.lower() in ("null", "incomplete"):
                date_obj = None
            elif rest.lower() == "today":
                date_obj = timezone.now().replace(hour=0, minute=0, second=0)
            elif rest.lower() == "yesterday":
                date_obj = timezone.now().replace(hour=0, minute=0, second=0)
                date_obj -= datetime.timedelta(days=1)
            else:
                try:
                    date_obj = dateutil.parser.parse(rest)
                except ValueError:
                    raise forms.ValidationError(f"Unable to parse {rest!r}")
                if timezone.is_naive(date_obj):
                    date_obj = timezone.make_aware(date_obj)
            dates.append((operator, date_obj.date()))

        return dates

    def clean_modified_at(self):
        return self._clean_dates(self.cleaned_data["modified_at"])

    def clean_sort(self):
        value = self.cleaned_data["sort"]
        if value and value not in ["modified_at", "created_at"]:
            raise forms.ValidationError(f"Invalid sort '{value}'")
        return value

    def clean_reverse(self):
        value = self.cleaned_data["reverse"]
        if value:
            return value == "true"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("sort"):
            cleaned["order_by"] = {
                "sort": cleaned.pop("sort"),
                "reverse": cleaned.pop("reverse"),
            }
        return cleaned
