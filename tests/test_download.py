# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.


import requests_mock
from markus.testing import MetricsMock
from markus import TIMING, HISTOGRAM
from django.core.urlresolvers import reverse


def test_happy_path(client):
    with requests_mock.mock() as m, MetricsMock() as metrics_mock:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Symbol Stuff\n'
        )
        m.head(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b''
        )
        url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym',
        ))
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == b'Symbol Stuff\n'

        response = client.head(url)
        assert response.status_code == 200
        assert response.content == b''

        metrics_mock.print_records()

        metrics_mock.has_record(
            HISTOGRAM,
            'tecken.download_symbols_size',
            len(b'Symbol Stuff\n'),
            ['s3.example.com']
        )
        metrics_records = metrics_mock.get_records()
        timing_metrics = [
            (thing, stat, value, tags)
            for thing, stat, value, tags in metrics_records
            if thing == TIMING
        ]
        assert len(timing_metrics) == 2
        assert timing_metrics[0][1] == 'tecken.download_symbol'
        assert timing_metrics[1][1] == 'tecken.download_symbol'
        assert isinstance(timing_metrics[0][2], float)
        assert isinstance(timing_metrics[1][2], float)


def test_404(client):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Not found',
            status_code=404
        )
        url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym',
        ))
        response = client.get(url)
        assert response.status_code == 404
        assert 'Page not found' in response.content.decode('utf-8')


def test_try_multiple_urls(client, settings):
    assert len(settings.SYMBOL_URLS) == 1
    settings.SYMBOL_URLS = [
        settings.SYMBOL_URLS[0],
        settings.SYMBOL_URLS[0].replace('s3', 's4')
    ]
    with requests_mock.mock() as m, MetricsMock() as metrics_mock:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Not found',
            status_code=404
        )
        m.head(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Not found',
            status_code=404
        )
        m.get(
            'https://s4.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Symbol Stuff\n'
        )
        m.head(
            'https://s4.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b''
        )
        url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym',
        ))
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == b'Symbol Stuff\n'

        response = client.head(url)
        assert response.status_code == 200
        assert response.content == b''

        metrics_mock.has_record(
            HISTOGRAM,
            'tecken.download_symbols_size',
            len(b'Symbol Stuff\n'),
            # Because it only worked eventually with that domain
            ['s4.example.com']
        )


def test_proxied_headers(client):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Symbol Stuff\n',
            headers={
                'Other': 'Junk',
                'ETag': 'abc123',
                'content-length': '12345',
            },
        )
        url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym',
        ))
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == b'Symbol Stuff\n'
        # It should have the standard headers our Django always puts in
        assert 'content-length' in response
        assert 'other' not in response
        assert response['x-frame-options']
        assert response['etag'] == 'abc123'
        assert response['Content-length'] == '12345'


def test_uppercase_debug_id(client):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Symbol Stuff\n'
        )
        url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44e4ec8c2f41492b9369d6b9a059577c2',  # lowercase!
            'xul.sym',
        ))
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == b'Symbol Stuff\n'


def test_product_prefix(client):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            content=b'Symbol Stuff\n'
        )
        original_url = reverse('download:download_symbol', args=(
            'xul.pdb',
            '44e4ec8c2f41492b9369d6b9a059577c2',  # lowercase!
            'xul.sym',
        ))
        url = '/firefox' + original_url
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == b'Symbol Stuff\n'

        url = '/waterwolf' + original_url
        response = client.get(url)
        assert response.status_code == 404
