# Derived from the "testprovider" container from
# https://github.com/mozilla-parsys/docker-test-mozilla-django-oidc.
# Only the redirect_urls specified in "fixtures.json" are being
# modified to fit the needs of the docker setup.

FROM mozillaparsys/oidc_testprovider@sha256:6205ab3f64fad52e005955ec0b3e19f1efebebea8a84a28cc19632cf6296a503

COPY fixtures.json /code/fixtures.json
