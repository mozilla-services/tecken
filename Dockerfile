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
        postgresql-client gettext libffi-dev jed

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


# Install node from NodeSource
#RUN curl -s https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add - && \
#    echo 'deb https://deb.nodesource.com/node_4.x jessie main' > /etc/apt/sources.list.d/nodesource.list && \
#    echo 'deb-src https://deb.nodesource.com/node_4.x jessie main' >> /etc/apt/sources.list.d/nodesource.list && \
#    apt-get update && apt-get install -y nodejs

# Create static and npm roots
#RUN mkdir -p /opt/npm /opt/static && \
#    chown -R 10001:10001 /opt

# Install Node 6
# From: https://github.com/nodejs/docker-node/blob/bb200caf20280e436dedc56a5f194fd21e684758/6.11/Dockerfile
# ...

# gpg keys listed at https://github.com/nodejs/node#release-team
RUN set -ex \
  && for key in \
    9554F04D7259F04124DE6B476D5A82AC7E37093B \
    94AE36675C464D64BAFA68DD7434390BDBE9B9C5 \
    FD3A5288F042B6850C66B31F09FE44734EB7990E \
    71DCFD284A79C3B38668286BC97EC7A07EDE3FC1 \
    DD8F2338BAE7501E3DD5AC78C273792F7D83545D \
    B9AE9905FFD7803F25714661B63B535A4C206CA9 \
    C4F0DFFF4E8C1A8236409D08E73BC641CC11F4C8 \
    56730D5401028683275BD23C23EFEFE93C4CFFFE \
  ; do \
    gpg --keyserver pgp.mit.edu --recv-keys "$key" || \
    gpg --keyserver keyserver.pgp.com --recv-keys "$key" || \
    gpg --keyserver ha.pool.sks-keyservers.net --recv-keys "$key" ; \
  done

ENV NPM_CONFIG_LOGLEVEL info
ENV NODE_VERSION 6.11.1

RUN curl -SLO "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" \
  && curl -SLO --compressed "https://nodejs.org/dist/v$NODE_VERSION/SHASUMS256.txt.asc" \
  && gpg --batch --decrypt --output SHASUMS256.txt SHASUMS256.txt.asc \
  && grep " node-v$NODE_VERSION-linux-x64.tar.xz\$" SHASUMS256.txt | sha256sum -c - \
  && tar -xJf "node-v$NODE_VERSION-linux-x64.tar.xz" -C /usr/local --strip-components=1 \
  && rm "node-v$NODE_VERSION-linux-x64.tar.xz" SHASUMS256.txt.asc SHASUMS256.txt \
  && ln -s /usr/local/bin/node /usr/local/bin/nodejs

ENV YARN_VERSION 0.24.6

RUN set -ex \
  && for key in \
    6A010C5166006599AA17F08146C2130DFD2497F5 \
  ; do \
    gpg --keyserver pgp.mit.edu --recv-keys "$key" || \
    gpg --keyserver keyserver.pgp.com --recv-keys "$key" || \
    gpg --keyserver ha.pool.sks-keyservers.net --recv-keys "$key" ; \
  done \
  && curl -fSLO --compressed "https://yarnpkg.com/downloads/$YARN_VERSION/yarn-v$YARN_VERSION.tar.gz" \
  && curl -fSLO --compressed "https://yarnpkg.com/downloads/$YARN_VERSION/yarn-v$YARN_VERSION.tar.gz.asc" \
  && gpg --batch --verify yarn-v$YARN_VERSION.tar.gz.asc yarn-v$YARN_VERSION.tar.gz \
  && mkdir -p /opt/yarn \
  && tar -xzf yarn-v$YARN_VERSION.tar.gz -C /opt/yarn --strip-components=1 \
  && ln -s /opt/yarn/bin/yarn /usr/local/bin/yarn \
  && ln -s /opt/yarn/bin/yarn /usr/local/bin/yarnpkg \
&& rm yarn-v$YARN_VERSION.tar.gz.asc yarn-v$YARN_VERSION.tar.gz


# ...End of Node 6 install steps.


# Install Python dependencies
COPY requirements.txt /tmp/
# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp
RUN pip install --no-cache-dir -r requirements.txt

# Install frontend dependencies using NPM
#COPY package.json /opt/npm/

# Switch to /opt/npm to install dependencies outside home dir
#WORKDIR /opt/npm
#RUN npm install && \
#    chown -R 10001:10001 /opt/npm && \
#    npm cache clean

# Build the frontend bundle in /tmp
#COPY frontend /tmp/frontend
#WORKDIR /tmp/frontend
#RUN yarn && yarn run build && yarn cache clean

#WORKDIR /opt/npm
#COPY frontend /opt/npm
#WORKDIR /opt/npm/frontend
#RUN yarn && chown -R 10001:10001 /opt/npm && yarn cache ls && yarn run build
#ADD frontend/package.json /tmp/package.json
#RUN cd /tmp && yarn && yarn build
#RUN mkdir -p /opt/app && cp -a /tmp/node_modules /opt/app/

# Switch back to home directory
WORKDIR /app

COPY . /app
#COPY /tmp/frontend/build /app/frontend/build

RUN chown -R 10001:10001 /app

USER 10001

#RUN DJANGO_CONFIGURATION=Build && \
#    python manage.py collectstatic --noinput

#WORKDIR /app/frontend
#RUN yarn && yarn run build && yarn cache clean && rm node_modules
#WORKDIR /app

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/run"]

CMD ["web"]
