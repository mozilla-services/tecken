FROM mozilla/oidc-testprovider:oidc_testprovider-v0.10.10@sha256:5a35b8cfc2abf8014db83a828a0edb1f4cb060975d81dd3d75363e875e5a4857

# Modify redirect_urls specified in "fixtures.json" to fit our needs.
COPY fixtures.json /code/fixtures.json

CMD ["./bin/run.sh"]
