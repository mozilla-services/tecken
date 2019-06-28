# Derived from the "testprovider" container from
# https://github.com/mozilla-parsys/docker-test-mozilla-django-oidc.
# Only the redirect_urls specified in "fixtures.json" are being
# modified to fit the needs of the docker setup.

FROM mozillaparsys/oidc_testprovider@sha256:876268f57a7932b3fc671bdb70eb79bfb283e567a13ff5ba2616af876554a8f3

COPY fixtures.json /code/fixtures.json
