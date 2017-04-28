# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from urllib.parse import urlparse

from markus import TIMING
from django.core.urlresolvers import reverse

from tecken.download.views import SymbolDownloader


def test_client_happy_path(client, s3_client, metricsmock):
    # s3 = boto3.client('s3', region_name='us-west-2')
    s3_client.create_bucket(Bucket='public')
    s3_client.put_object(
        Bucket='public',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    response = client.get(url)
    assert response.status_code == 302
    parsed = urlparse(response['location'])
    # the pre-signed URL will have the bucket in the domain
    assert parsed.netloc == 'public.s3.amazonaws.com'
    assert parsed.path == (
        '/prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
    )
    assert 'Signature=' in parsed.query
    assert 'Expires=' in parsed.query
    assert 'AWSAccessKeyId=' in parsed.query

    response = client.head(url)
    assert response.status_code == 200
    assert response.content == b''

    print(metricsmock.print_records())
    metrics_records = metricsmock.get_records()
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


def test_client_404(client, s3_client):
    s3_client.create_bucket(Bucket='public')

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    response = client.get(url)
    assert response.status_code == 404
    assert 'Page not found' in response.content.decode('utf-8')


def test_multiple_urls(settings, s3_client):
    urls = [
        settings.SYMBOL_URLS[0],
        settings.SYMBOL_URLS[0].replace('public', 'additional')
    ]
    s3_client.create_bucket(Bucket='public')
    s3_client.create_bucket(Bucket='additional')
    s3_client.put_object(
        Bucket='additional',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    url = downloader.get_symbol_url(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    assert url
    assert url.startswith('https://additional.s3.amazonaws.com')


def test_uppercase_debug_id(settings, s3_client):
    s3_client.create_bucket(Bucket='public')
    s3_client.put_object(
        Bucket='public',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    assert downloader.has_symbol(
        'xul.pdb',
        '44e4ec8c2f41492b9369d6b9a059577c2',
        'xul.sym'
    )


def test_product_no_prefix(settings, s3_client):
    s3_client.create_bucket(Bucket='public')
    s3_client.put_object(
        Bucket='public',
        Key='xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    url = settings.SYMBOL_URLS[0]
    url = url.replace('/prefix/', '')
    downloader = SymbolDownloader([url])
    assert downloader.has_symbol(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
