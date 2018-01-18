FROM node:6.12.3 as frontend

# these build args are turned into env vars
# and used in bin/build_frontend.sh
ARG FRONTEND_SENTRY_PUBLIC_DSN=UNSET_DSN
ENV FRONTEND_SENTRY_PUBLIC_DSN=${FRONTEND_SENTRY_PUBLIC_DSN}
ARG CI=false
ENV CI=${CI}

RUN echo "Running in CI: ${CI}"

COPY . /app
WORKDIR /app
RUN bin/build_frontend.sh

FROM python:3.6-slim
MAINTAINER Peter Bengtsson <peterbe@mozilla.com>

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/ \
    DJANGO_CONFIGURATION=Prod \
    PORT=8000

EXPOSE $PORT

# add a non-privileged user for installing and running the application
# don't use --create-home option to prevent populating with skeleton files
RUN mkdir /app && \
    chown 10001:10001 /app && \
    groupadd --gid 10001 app && \
    useradd --no-create-home --uid 10001 --gid 10001 --home-dir /app app

# install a few essentials and clean apt caches afterwards
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-transport-https build-essential curl git libpq-dev \
        gettext libffi-dev jed

# Install dump_syms
RUN DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
        gyp ninja-build binutils-gold gcc-4.8 g++-4.8 pkg-config cabextract
COPY ./docker/build_dump_syms.sh /tmp
RUN /tmp/build_dump_syms.sh

# Clean up apt
RUN apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies
COPY requirements.txt /tmp/
# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Switch back to home directory
WORKDIR /app

# Copy static assets
COPY --from=frontend /app/frontend/build /app/frontend/build

RUN chown -R 10001:10001 /app

USER 10001

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/run.sh"]

CMD ["web"]
