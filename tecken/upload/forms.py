# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError

from django import forms
from django.conf import settings


class UploadByDownloadForm(forms.Form):
    url = forms.URLField()

    def clean_url(self):
        url = self.cleaned_data['url']
        # The URL has to be https:// to start with
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            raise forms.ValidationError('Insecure URL')

        netloc_wo_port = parsed.netloc.split(':')[0]
        if netloc_wo_port not in settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS:
            raise forms.ValidationError(
                f'Not an allowed domain ({netloc_wo_port}) to download from'
            )
        return url

    def clean(self):
        cleaned_data = super().clean()
        if 'url' in cleaned_data:
            url = cleaned_data['url']
            parsed = urlparse(url)
            try:
                response = requests.head(url)
            except ConnectionError:
                raise forms.ValidationError(
                    f'ConnectionError trying to open {url}'
                )
            if response.status_code != 200:
                raise forms.ValidationError(
                    f"{url} can't be found ({response.status_code})"
                )
            content_length = response.headers['content-length']
            cleaned_data['upload'] = {
                'name': os.path.basename(parsed.path),
                'size': int(content_length),
            }
        return cleaned_data
