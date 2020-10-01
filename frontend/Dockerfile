# Note! If you make changes it in this file, to rebuild it use:
#   docker-compose build frontend
#

# This should match what we have in the Node section of the main Dockerfile.
FROM node:14.7.0-slim@sha256:684feb573d3e0433f05e2ca9d71c46997f6f9a9610ccb46705a0385c46d8c427 as frontend

ARG userid=10001
ARG groupid=10001

ENV NODE_PATH=/node_modules
ENV PATH=$PATH:/node_modules/.bin

WORKDIR /app

# add a non-privileged user for installing and running the application only if the
# userid is not 1000 because node already has one
RUN if [ $userid -ne 1000 ]; then \
        groupadd --gid $groupid app; \
        useradd -g app --uid $userid --shell /usr/sbin/nologin --create-home app; \
        chown app:app /app/; \
    fi

ADD frontend/yarn.lock /yarn.lock
ADD frontend/package.json /package.json
RUN yarn

ADD frontend /app

EXPOSE 3000
EXPOSE 35729

# NOTE(willkg): use $userid here because we don't know what the user name is
USER $userid

ENTRYPOINT ["/bin/bash", "/app/bin/run_frontend.sh"]
CMD ["start"]
