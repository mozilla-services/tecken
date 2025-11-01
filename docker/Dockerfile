# NOTE(willkg): Make sure to update frontend/Dockerfile when you update this
#
# NOTE(willkg): We're using node 14 because of this issue:
# https://github.com/docker/for-mac/issues/5831
FROM --platform=linux/amd64 node:16.10.0-slim@sha256:9bec98898848c3e3a1346bc74ab04c2072da9d0149d8be1ea0485dbf39fd658f as frontend

COPY . /app
WORKDIR /app
RUN bin/build_frontend.sh


# NOTE(smarnach): To upgrade Python to a new minor or major version, see
# https://tecken.readthedocs.io/en/latest/dev.html#how-to-upgrade-the-python-version
FROM --platform=linux/amd64 python:3.11.14-slim-bookworm@sha256:e5b49052cdc5d8223d037a718e3cecd4169f41701e03d0baf5c994bf19522bf4

ARG userid=10001
ARG groupid=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/ \
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
        apt-transport-https \
        build-essential \
        curl \
        git \
        libpq-dev \
        gettext \
        libffi-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies
COPY requirements.txt /tmp/
# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp

RUN pip install -U 'pip>=20' && \
    pip install --no-cache-dir --no-deps -r requirements.txt && \
    pip check --disable-pip-version-check

COPY . /app

# Switch back to home directory
WORKDIR /app

# Copy static assets
COPY --from=frontend /app/frontend/build /app/frontend/build
RUN /app/bin/run_collectstatic.sh

RUN chown -R app:app /app

USER app

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]

CMD ["web"]
