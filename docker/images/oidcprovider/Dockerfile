FROM mozilla/oidc-testprovider:oidc_testprovider-0.10.12@sha256:975d5efd8636b2200eefef8d07505c3f0425c0893cfd2e326d73fa074597c62d

# Modify redirect_urls specified in "fixtures.json" to fit our needs.
COPY fixtures.json /code/fixtures.json

CMD ["./bin/run.sh"]
