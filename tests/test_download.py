# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from urllib.parse import urlparse

from markus import TIMING
from django.core.urlresolvers import reverse


def test_client_happy_path(client, s3_client, metricsmock, settings):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/private/prefix/',
    )
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
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
    assert parsed.netloc == 'private.s3.amazonaws.com'
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


def test_client_404(client, s3_client, settings):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/private/prefix/',
    )
    s3_client.create_bucket(Bucket='private')
    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    response = client.get(url)
    assert response.status_code == 404
    assert 'Symbol Not Found' in response.content.decode('utf-8')

    response = client.head(url)
    assert response.status_code == 404
