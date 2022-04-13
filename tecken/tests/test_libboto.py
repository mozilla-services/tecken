# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pickle

from tecken.libboto import (
    OwnEndpointConnectionError,
    OwnClientError,
)


def test_pickle_OwnEndpointConnectionError():
    """test that it's possible to pickle, and unpickle an instance
    of a OwnEndpointConnectionError exception class."""
    exception = OwnEndpointConnectionError(endpoint_url="http://example.com")
    pickled = pickle.dumps(exception)
    exception = pickle.loads(pickled)
    # They can't be compared, but...
    assert exception.msg == exception.msg
    assert exception.kwargs == exception.kwargs
    assert exception.fmt == exception.fmt


def test_pickle_OwnClientError():
    """test that it's possible to pickle, and unpickle an instance
    of a OwnClientError exception class."""
    exception = OwnClientError({"Error": {"Code": "123"}}, "PutObject")
    pickled = pickle.dumps(exception)
    exception = pickle.loads(pickled)
    # They can't be compared, but...
    assert exception.response == exception.response
    assert exception.operation_name == exception.operation_name
