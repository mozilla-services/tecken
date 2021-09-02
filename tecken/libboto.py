# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from botocore.exceptions import EndpointConnectionError, ClientError


# FIXME(willkg): 1728210: remove this after we remove celery infra


class OwnEndpointConnectionError(EndpointConnectionError):
    """Because the botocore.exceptions.EndpointConnectionError can't be
    pickled, if this exception happens during task work, celery
    won't be able to pickle it. So we write our own.

    See https://github.com/boto/botocore/pull/1191 for a similar problem
    with the ClientError exception.
    """

    def __init__(self, msg=None, **kwargs):
        if not msg:
            msg = self.fmt.format(**kwargs)
        Exception.__init__(self, msg)
        self.kwargs = kwargs
        self.msg = msg

    def __reduce__(self):
        return (self.__class__, (self.msg,), {"kwargs": self.kwargs})


class OwnClientError(ClientError):  # XXX Replace "Own" with "Picklable" ?
    """Because the botocore.exceptions.EndpointConnectionError can't be
    pickled, if this exception happens during task work, celery
    won't be able to pickle it. So we write our own.

    See https://github.com/boto/botocore/pull/1191
    """

    def __reduce__(self):
        return (self.__class__, (self.response, self.operation_name), {})
