# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
This is based on django-file-resubmit, which is MIT licensed:

Copyright (C) 2011 by Ilya Shalyapin, ishalyapin@gmail.com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from io import BytesIO

from django.core.cache import caches
from django.core.files.uploadedfile import InMemoryUploadedFile


class CachedFileCache:
    def __init__(self):
        self.backend = self.get_backend()

    def get_backend(self):
        return caches['default']

    def prefix(self, key):
        return 'cachedfile_' + key

    def store(self, key, upload):
        metadata = {
            'name': upload.name,
            'size': upload.size,
            'content_type': upload.content_type,
            'charset': upload.charset,
        }
        self.backend.set(self.prefix(key) + '_metadata', metadata)
        upload.file.seek(0)
        content = upload.file.read()
        upload.file.seek(0)
        self.backend.set(self.prefix(key) + '_content', content)

    def metadata(self, key):
        return self.backend.get(self.prefix(key) + '_metadata')

    def retrieve(self, key, field_name):
        metadata = self.metadata(key)
        content = self.backend.get(self.prefix(key) + '_content')
        if metadata and content:
            out = BytesIO()
            out.write(content)
            upload = InMemoryUploadedFile(
                file=out,
                field_name=field_name,
                name=metadata['name'],
                content_type=metadata['content_type'],
                size=metadata['size'],
                charset=metadata['charset'],
            )
            upload.file.seek(0)
        else:
            upload = None
        return upload

    def remove(self, key):
        for suffix in ['_metadata', '_content']:
            self.backend.delete(self.prefix(key) + suffix)
