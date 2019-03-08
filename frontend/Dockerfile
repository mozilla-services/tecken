# Note! If you make changes it in this file, to rebuild it use:
#   docker-compose build frontend
#

# This should match what we have in the Node section of the main Dockerfile.
FROM node:10.15.3-slim@sha256:477035dd1421cb62aea19cec1dca7a780b215971f3085b1951573a936cf96ee7

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
