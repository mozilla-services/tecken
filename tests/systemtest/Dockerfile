FROM python:3.6-slim
MAINTAINER Peter Bengtsson <peterbe@mozilla.com>

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/


# add a non-privileged user for installing and running the application
# don't use --create-home option to prevent populating with skeleton files
RUN mkdir /app && \
    chown 10001:10001 /app && \
    groupadd --gid 10001 app && \
    useradd --no-create-home --uid 10001 --gid 10001 --home-dir /app app

# Install Python dependencies
COPY tests/systemtest/requirements.txt /tmp/

# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp
RUN pip install --no-cache-dir -r requirements.txt

# Switch back to home directory
WORKDIR /app

COPY . /app

RUN chown -R 10001:10001 /app

USER 10001
