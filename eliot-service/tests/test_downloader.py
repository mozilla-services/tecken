# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from eliot.downloader import (
    ErrorFileNotFound,
    FileNotFound,
    HTTPSource,
    SymbolFileDownloader,
)


FAKE_HOST = "http://example.com"
FAKE_HOST2 = "http://2.example.com"


class TestHTTPSource:
    def test_get(self, requestsmock):
        data = b"abcde"
        requestsmock.get(
            FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=200, content=data
        )

        source = HTTPSource(FAKE_HOST)
        ret = source.get("xul.so", "ABCDE", "xul.sym")
        assert ret == data
        assert type(ret) == type(data)

    def test_get_404(self, requestsmock):
        requestsmock.get(FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=404)

        source = HTTPSource(FAKE_HOST)
        with pytest.raises(FileNotFound):
            source.get("xul.so", "ABCDE", "xul.sym")

    def test_get_500(self, requestsmock):
        requestsmock.get(FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=500)

        source = HTTPSource(FAKE_HOST)
        with pytest.raises(ErrorFileNotFound):
            source.get("xul.so", "ABCDE", "xul.sym")


class TestSymbolFileDownloader:
    def test_get(self, requestsmock):
        data_1 = b"abcde"
        data_2 = b"12345"
        requestsmock.get(
            FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=200, content=data_1
        )
        requestsmock.get(
            FAKE_HOST2 + "/xul.so/ABCDE/xul.sym", status_code=200, content=data_2
        )

        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST, FAKE_HOST2])
        ret = downloader.get("xul.so", "ABCDE", "xul.sym")
        assert ret == data_1

    def test_get_from_second(self, requestsmock):
        data = b"abcde"
        requestsmock.get(FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=404)
        requestsmock.get(
            FAKE_HOST2 + "/xul.so/ABCDE/xul.sym", status_code=200, content=data
        )

        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST, FAKE_HOST2])
        ret = downloader.get("xul.so", "ABCDE", "xul.sym")
        assert ret == data

    def test_404(self, requestsmock):
        requestsmock.get(FAKE_HOST + "/xul.so/ABCDE/xul.sym", status_code=404)
        requestsmock.get(FAKE_HOST2 + "/xul.so/ABCDE/xul.sym", status_code=404)

        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST, FAKE_HOST2])
        with pytest.raises(FileNotFound):
            downloader.get("xul.so", "ABCDE", "xul.sym")
