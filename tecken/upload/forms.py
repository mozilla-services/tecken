import datetime

from django import forms
from django.utils import timezone


class SearchForm(forms.Form):
    user = forms.CharField(required=False)
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)

    def clean_start_date(self):
        if self.cleaned_data.get('start_date'):
            return self._make_timezone_aware(self.cleaned_data['start_date'])

    def clean_end_date(self):
        if self.cleaned_data.get('end_date'):
            return self._make_timezone_aware(self.cleaned_data['end_date'])

    @staticmethod
    def _make_timezone_aware(date):
        return timezone.make_aware(
            datetime.datetime.combine(date, datetime.datetime.min.time())
        )
