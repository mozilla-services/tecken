# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import mock

from tecken.s3 import S3Bucket


def test_use_s3bucket():
    bucket = S3Bucket('https://s3.amazonaws.com/some-bucket')
    assert bucket.name == 'some-bucket'
    assert bucket.endpoint_url is None
    assert bucket.region is None
    assert bucket.private  # because it's the default
    assert str(bucket) == 'https://s3.amazonaws.com/some-bucket/'

    bucket = S3Bucket(
        'https://s3.amazonaws.com/some-bucket?access=public'
    )
    assert bucket.name == 'some-bucket'
    assert bucket.endpoint_url is None
    assert bucket.region is None
    assert not bucket.private
    assert str(bucket) == 'https://s3.amazonaws.com/some-bucket/'

    bucket = S3Bucket('https://s3-us-north-2.amazonaws.com/some-bucket')
    assert bucket.name == 'some-bucket'
    assert bucket.endpoint_url is None
    assert bucket.region == 'us-north-2'
    assert str(bucket) == 'https://s3-us-north-2.amazonaws.com/some-bucket/'

    bucket = S3Bucket('http://s3.example.com/buck/prfx')
    assert bucket.name == 'buck'
    assert bucket.endpoint_url == 'http://s3.example.com'
    assert bucket.region is None
    assert bucket.prefix == 'prfx'
    assert str(bucket) == 'http://s3.example.com/buck/prfx'

    # Just check that __repr__ it works at all
    assert repr(bucket)


def test_s3bucket_client():
    mock_session = mock.Mock()

    def new_session():
        return mock_session

    with mock.patch('tecken.s3.boto3.session.Session', new=new_session):
        bucket = S3Bucket('https://s3.amazonaws.com/some-bucket')
        client = bucket.s3_client
        client_again = bucket.s3_client
        assert client_again is client
        # Only 1 session should have been created
        assert len(mock_session.mock_calls) == 1
        mock_session.client.assert_called_with('s3')

        # make a client that requires an endpoint_url
        bucket = S3Bucket('http://s3.example.com/buck/prefix')
        bucket.s3_client
        mock_session.client.assert_called_with(
            's3',
            endpoint_url='http://s3.example.com',
        )

        # make a client that requires a different region
        bucket = S3Bucket('https://s3-us-north-2.amazonaws.com/some-bucket')
        bucket.s3_client
        mock_session.client.assert_called_with(
            's3',
            region_name='us-north-2',
        )
