FROM node:14.7.0-slim@sha256:684feb573d3e0433f05e2ca9d71c46997f6f9a9610ccb46705a0385c46d8c427 as frontend

# these build args are turned into env vars
# and used in bin/build_frontend.sh
ARG FRONTEND_SENTRY_PUBLIC_DSN=UNSET_DSN
ENV FRONTEND_SENTRY_PUBLIC_DSN=${FRONTEND_SENTRY_PUBLIC_DSN}

COPY . /app
WORKDIR /app
RUN bin/build_frontend.sh


FROM python:3.8.5-slim@sha256:282fc7428f74cf3317d78224349b9215f266fc9cb4197cce58dad775cb565ed3

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
    gettext libffi-dev

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
RUN /app/bin/run_collectstatic.sh

RUN chown -R app:app /app

USER app

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]

CMD ["web"]
