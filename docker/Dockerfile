FROM node:14.1.0-slim@sha256:56b4c785d588bffee421dd194710ac7379f35987c007e76f0b25bb3130dd64df as frontend

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

# NOTE(willkg): stick with stretch because it has gcc-6 which we need
# to build dump_syms.
FROM python:3.7.7-slim-stretch@sha256:3b072d391496e120bd25025462489b8a437f17135dda96f765de5d0a0e159fa3

ARG userid=10001
ARG groupid=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/ \
    DJANGO_CONFIGURATION=Prod \
    PORT=8000

EXPOSE $PORT

WORKDIR /app

# add a non-privileged user for installing and running the application
RUN groupadd --gid $groupid app && \
    useradd -g app --uid $userid --shell /usr/sbin/nologin --create-home app && \
    chown app:app /app/

# install a few essentials and clean apt caches afterwards
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https build-essential curl git libpq-dev \
    gettext libffi-dev jed

# Install dump_syms
RUN DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    gyp ninja-build binutils-gold gcc-6 g++-6 pkg-config cabextract
COPY ./docker/build_dump_syms.sh /tmp
RUN /tmp/build_dump_syms.sh

# Clean up apt
RUN apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies
COPY ./requirements /tmp/requirements
# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp
RUN pip install -U 'pip>=10' && \
    pip install --no-cache-dir -r requirements/default.txt && \
    pip check --disable-pip-version-check

COPY . /app

# Switch back to home directory
WORKDIR /app

# Copy static assets
COPY --from=frontend /app/frontend/build /app/frontend/build

RUN chown -R app:app /app

USER app

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/run.sh"]

CMD ["web"]
