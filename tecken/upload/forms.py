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
        url = self.cleaned_data["url"]
        # The URL has to be https:// to start with
        parsed = urlparse(url)
        if not settings.ALLOW_UPLOAD_BY_ANY_DOMAIN:
            if parsed.scheme != "https":
                raise forms.ValidationError("Insecure URL")
        self._check_url_domain(url)
        return url

    @staticmethod
    def _check_url_domain(url):
        netloc_wo_port = urlparse(url).netloc.split(":")[0]
        if not settings.ALLOW_UPLOAD_BY_ANY_DOMAIN:
            if netloc_wo_port not in settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS:
                raise forms.ValidationError(
                    f"Not an allowed domain ({netloc_wo_port!r}) " "to download from."
                )

    def clean(self):
        cleaned_data = super().clean()
        if "url" in cleaned_data:
            # In the main view code where the download actually happens,
            # it'll follow any redirects automatically, but we want to
            # do "recursive HEADs" to find out the size of the file.
            # It also gives us an opportunity to record the redirect trail.
            url = cleaned_data["url"]
            parsed = urlparse(url)
            response, redirect_urls = self.get_final_response(url)
            content_length = response.headers["content-length"]
            cleaned_data["upload"] = {
                "name": os.path.basename(parsed.path),
                "size": int(content_length),
                "redirect_urls": redirect_urls,
            }
        return cleaned_data

    @staticmethod
    def get_final_response(initial_url, max_redirects=5):
        """return the final response when it 200 OK'ed and a list of URLs
        that we had to go through redirects of."""
        redirect_urls = []  # the mutable "store"

        def get_response(url):
            try:
                response = requests.head(url)
                status_code = response.status_code
            except ConnectionError:
                raise forms.ValidationError(f"ConnectionError trying to open {url}")
            if status_code >= 500:
                raise forms.ValidationError(f"{url} errored ({status_code})")
            if status_code >= 400:
                raise forms.ValidationError(f"{url} can't be found ({status_code})")
            if status_code >= 300 and status_code < 400:
                redirect_url = response.headers["location"]
                redirect_urls.append(redirect_url)
                # Only do this if we haven't done it "too much" yet.
                if len(redirect_urls) > max_redirects:
                    raise forms.ValidationError(
                        f"Too many redirects trying to open {initial_url}"
                    )
                return get_response(redirect_url)
            assert status_code >= 200 and status_code < 300, status_code
            return response

        final_response = get_response(initial_url)

        return final_response, redirect_urls
