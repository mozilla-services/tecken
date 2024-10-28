FROM mozilla/oidc-testprovider:oidc_testprovider-v0.10.7@sha256:cff948eeb665cd48a6bd343af585f4970d2788a7745ea8c84410bf80800e0ef9

# Modify redirect_urls specified in "fixtures.json" to fit our needs.
COPY fixtures.json /code/fixtures.json

CMD ["./bin/run.sh"]
