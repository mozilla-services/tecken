# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import falcon


class IndexResource:
    def on_get(self, req, resp):
        resp.content_type = "text/html"
        resp.status = falcon.HTTP_200
        resp.body = "<html><body>Eliot Index</body></html>"
