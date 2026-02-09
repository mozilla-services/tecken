# NOTE(willkg): Make sure to update frontend/Dockerfile when you update this
#
# NOTE(willkg): We're using node 14 because of this issue:
# https://github.com/docker/for-mac/issues/5831
FROM --platform=linux/amd64 node:16.10.0-slim@sha256:9bec98898848c3e3a1346bc74ab04c2072da9d0149d8be1ea0485dbf39fd658f as frontend

COPY frontend /app/frontend
COPY bin/build_frontend.sh /app/bin/
WORKDIR /app
RUN bin/build_frontend.sh


# NOTE(smarnach): To upgrade Python to a new minor or major version, see
# https://tecken.readthedocs.io/en/latest/dev.html#how-to-upgrade-the-python-version
FROM --platform=linux/amd64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim@sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36
ARG userid=10001
ARG groupid=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/ \
    PORT=8000 \
    UV_PYTHON_DOWNLOADS=0

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

USER app

# Install Python dependencies
RUN --mount=type=cache,uid=$userid,gid=$groupid,target=/home/app/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=app:app . /app

# Copy static assets
COPY --from=frontend --chown=app:app /app/frontend/build /app/frontend/build
RUN /app/bin/run_collectstatic.sh

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]

CMD ["web"]
