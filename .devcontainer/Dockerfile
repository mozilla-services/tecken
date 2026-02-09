FROM --platform=linux/amd64 mcr.microsoft.com/devcontainers/python:3.11-bookworm@sha256:138c451b17c1c5930f77e71a6510a0bae1d7b77feff5e0a714a22fa3d757a51f

ARG userid=10001
ARG groupid=10001

WORKDIR /app

# Add a non-privileged user for installing and running the application.
# We use --non-unique in case $groupid/$userid collide with the existing "vscode" user.
# We use --shell /bin/bash because the default is /bin/sh which doesn't support arrow keys
RUN groupadd --gid $groupid --non-unique app && \
    useradd -g app --uid $userid --non-unique --shell /bin/bash --create-home app && \
    chown app:app /app/

# Install Debian packages
RUN apt-get update && \
    apt-get install -y ripgrep tig

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

USER app

# Install Python dependencies
RUN --mount=type=cache,uid=$userid,gid=$groupid,target=/home/app/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --group devcontainer
ENV PATH="/app/.venv/bin:$PATH"
