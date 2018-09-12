# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
from urllib.parse import urlparse

from requests.exceptions import ConnectionError, RetryError

from django import forms
from django.conf import settings

from tecken.base.utils import requests_retry_session


class UploadByDownloadRemoteError(Exception):
    """Happens when the upload-by-download URL is failing in a "transient" way.
    For example, if the URL (when GET'ing) causes a ConnectionError or if it works
    but returns a >=500 error. In those cases, we want to make sure the client
    is informed "more strongly" than just getting a "400 Bad Request".

    As a note;
    See https://dxr.mozilla.org/mozilla-central/rev/423bdf7a802b0d302244492b423609187de39f56/toolkit/crashreporter/tools/upload_symbols.py#116 # noqa
    The Taskcluster symbol uploader knows to retry on any 5xx error. That's
    meant to reflect 5xx in Tecken. But by carrying the 5xx from the
    upload-by-download URL, we're doing them a favor.
    """


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
                response = requests_retry_session().head(url)
                status_code = response.status_code
            except ConnectionError:
                raise UploadByDownloadRemoteError(
                    f"ConnectionError trying to open {url}"
                )
            except RetryError:
                raise UploadByDownloadRemoteError(f"RetryError trying to open {url}")
            if status_code >= 500:
                raise UploadByDownloadRemoteError(f"{url} errored ({status_code})")
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
