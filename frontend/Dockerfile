# Note! If you make changes it in this file, to rebuild it use:
#
#   docker compose build frontend
#

# This should match what we have in the Node section of the main Dockerfile.
FROM node:16.19.1-slim@sha256:1417528032837e47462ea8cfe983108b0152f989e95cba2ddfbe0f0ddc2dcfbd as frontend

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

# install tini
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-transport-https \
        tini && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD frontend/yarn.lock /yarn.lock
ADD frontend/package.json /package.json
RUN yarn

ADD frontend /app

EXPOSE 3000
EXPOSE 35729

# NOTE(willkg): use $userid here because we don't know what the user name is
USER $userid

ENTRYPOINT ["tini", "--", "/bin/bash", "/app/bin/run_frontend.sh"]
CMD ["start"]
