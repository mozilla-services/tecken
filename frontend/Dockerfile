# Note! If you make changes it in this file, to rebuild it use:
#   docker-compose build frontend
#

# This should match what we have in the Node section of the main Dockerfile.
FROM node:10.18.0-slim@sha256:7da09bec069149d866c112c6dffe6b5ef51e1bcc45afb88650e47055fef53c3f

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
