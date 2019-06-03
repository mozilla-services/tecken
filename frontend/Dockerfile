# Note! If you make changes it in this file, to rebuild it use:
#   docker-compose build frontend
#

# This should match what we have in the Node section of the main Dockerfile.
FROM node:10.15.3-slim@sha256:5177e5de0e87965ed102f5a84856e31c1434e479dd0d90cf8df21d61284c78f1

ADD frontend/yarn.lock /yarn.lock
ADD frontend/package.json /package.json
RUN yarn

ENV NODE_PATH=/node_modules
ENV PATH=$PATH:/node_modules/.bin
WORKDIR /app
ADD frontend /app

EXPOSE 3000
EXPOSE 35729


ENTRYPOINT ["/bin/bash", "/app/bin/run_frontend.sh"]
CMD ["start"]
