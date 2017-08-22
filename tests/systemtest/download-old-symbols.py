#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Script to generate a .zip file that will help make sure the Tecken instance's
S3 store has all the necessary symbols for the systemtests to work.

This depends on downloading the symbols from some S3 public bucket by HTTP
GET.
"""

import zipfile
import os
import tempfile

import requests


# This is the URL were we can expect to download all the symbols that
# the systemtests require.
LEGACY_S3_URL = (
    'https://s3-us-west-2.amazonaws.com/'
    'org.mozilla.crash-stats.symbols-public/'
)


# These are the known symbol paths that the tests/systemtests/test*.py
# depends on.
URLS = """

v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym
v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.pd_
#v1/libxul.so/20BC1801B0B1864324D3B9E933328A170/libxul.so.dbg.gz
# v1/XUL/E3532A114F1C37E2AF567D8E6975F80C0/XUL.dSYM.tar.bz2
v1/firefox/946C0C63132015DD88CA2EFCBB9AC4C70/firefox.sym
v1/firefox.exe/59021DD066000/firefox.ex_

v1/firefox.pdb/C617B8AF472444AD952D19A0CFD7C8F72/firefox.sym
v1/wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym

"""


def run():
    urls = [
        x.strip()
        for x in URLS.strip().splitlines()
        if x.strip() and not x.strip().startswith('#')
    ]

    with tempfile.TemporaryDirectory(prefix='symbols') as tmpdirname:
        downloaded = download_all(urls, tmpdirname)
        save_filepath = 'symbols-for-systemtests.zip'
        total_time_took = 0.0
        total_size = 0
        with zipfile.ZipFile(save_filepath, mode='w') as zf:
            for uri, (fullpath, time_took, size) in downloaded.items():
                total_time_took += time_took
                total_size += size
                if fullpath:
                    path = uri.replace('v1/', '')
                    assert os.path.isfile(fullpath)
                    zf.write(
                        fullpath,
                        arcname=path,
                        compress_type=zipfile.ZIP_DEFLATED,
                    )


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return '%3.1f%s%s' % (num, unit, suffix)
        num /= 1024.0
    return '%.1f%s%s' % (num, 'Yi', suffix)


def download(uri, save_dir, store):
    url = LEGACY_S3_URL + uri
    response = requests.get(url)
    response.raise_for_status()
    path = uri
    dirname = os.path.join(save_dir, os.path.dirname(path))
    os.makedirs(dirname, exist_ok=True)
    basename = os.path.basename(path)
    fullpath = os.path.join(dirname, basename)
    print(
        response.status_code,
        sizeof_fmt(int(response.headers['Content-Length'])).ljust(10),
        url,
    )
    with open(fullpath, 'wb') as f:
        f.write(response.content)


def download_all(urls, save_dir):
    print('Downloading into...', save_dir)
    downloaded = {x: False for x in urls}
    for url in urls:
        download(url, save_dir, downloaded)
    return downloaded


if __name__ == '__main__':
    run()
