# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from tecken import dockerflow_extra


def test_check_redis_store_connected_happy_path():
    assert not dockerflow_extra.check_redis_store_connected(None)


def test_check_s3_urls_happy_path(botomock, settings):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'HeadBucket'
        # These come from settings.Test
        fixture_bucket_names = (
            'private',
            'mybucket',
            'peterbe-com',
        )
        assert api_params['Bucket'] in fixture_bucket_names
        return {}

    with botomock(mock_api_call):
        assert not dockerflow_extra.check_s3_urls(None)


def test_check_s3_urls_client_error(botomock, settings):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'HeadBucket'
        if api_params['Bucket'] == 'private':
            response = {'Error': {'Code': '404', 'Message': 'Not found'}}
            raise ClientError(response, operation_name)
        return {}

    with botomock(mock_api_call):
        errors = dockerflow_extra.check_s3_urls(None)
        assert errors
        error, = errors
        assert 'private' in error.msg
        assert 'ClientError' in error.msg


def test_check_s3_urls_endpointconnectionerror(botomock, settings):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'HeadBucket'
        if api_params['Bucket'] == 'private':
            raise EndpointConnectionError(endpoint_url='http://s3.example.com')
        return {}

    with botomock(mock_api_call):
        errors = dockerflow_extra.check_s3_urls(None)
        assert errors
        error, = errors
        assert 'private' in error.msg
        assert 'EndpointConnectionError' in error.msg


def test_check_s3_urls_other_client_error(botomock, settings):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'HeadBucket'
        if api_params['Bucket'] == 'private':
            response = {'Error': {'Code': '500', 'Message': 'Other'}}
            raise ClientError(response, operation_name)
        return {}

    with botomock(mock_api_call):
        with pytest.raises(ClientError):
            dockerflow_extra.check_s3_urls(None)
