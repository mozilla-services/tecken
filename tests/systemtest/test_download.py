# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import requests

BASE_URL = os.environ.get('BASE_URL')
assert BASE_URL


def _test(uri, firstline=None):
    assert uri.startswith('/')
    url = BASE_URL + uri
    if firstline:
        function = requests.get
    else:
        function = requests.head
    # This short timeout might make this unpractical for people
    # running these tests on laptops in bad network environments.
    # Arguably, if that's the case, perhaps don't run these tests.
    response = function(url, timeout=10)
    assert response.status_code == 200

    if firstline:
        assert firstline == response.text.splitlines()[0]


def test_basic_get():
    _test(
        '/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym',
        'MODULE windows x86 448794C699914DB8A8F9B9F88B98D7412 firefox.pdb'
    )


def test_basic_pdb():
    # Basic GET of a native debug symbols file for Windows/Linux/Mac
    _test('/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.pd_')


def test_basic_dbg():
    _test('/libxul.so/20BC1801B0B1864324D3B9E933328A170/libxul.so.dbg.gz')


def test_basic_dsym():
    _test('/XUL/E3532A114F1C37E2AF567D8E6975F80C0/XUL.dSYM.tar.bz2')


def test_mixed_case():
    """bug 660932, bug 414852"""
    _test(
        '/firefox.pdb/448794c699914db8a8f9b9f88b98d7412/firefox.sym',
        'MODULE windows x86 448794C699914DB8A8F9B9F88B98D7412 firefox.pdb'
    )


def test_old_firefox_prefix():
    _test(
        '/firefox/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym',
        'MODULE windows x86 448794C699914DB8A8F9B9F88B98D7412 firefox.pdb'
    )


def test_old_thunderbird_prefix():
    # Yes, this looks dumb.
    _test(
        (
            '/thunderbird/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/'
            'firefox.sym'
        ),
        'MODULE windows x86 448794C699914DB8A8F9B9F88B98D7412 firefox.pdb'
    )


def test_firefox_without_prefix():
    """
    bug 1246151 - The firefox binary on Linux/Mac is just named `firefox`,
    so make sure the rewrite rules to strip the app name don't
    break downloading these files.
    """
    _test(
        '/firefox/946C0C63132015DD88CA2EFCBB9AC4C70/firefox.sym',
        'MODULE Linux x86_64 946C0C63132015DD88CA2EFCBB9AC4C70 firefox'
    )


def test_non_symbol_debug_files():
    """
    Some files are debug files that aren't plain symbols. These are
    different from regular symbols in that they have a much shorter
    debug ID.
    """
    _test(
        '/firefox.exe/59021DD066000/firefox.ex_'
    )
