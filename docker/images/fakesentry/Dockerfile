FROM python:3.11.6-slim-bullseye@sha256:44c644f4146ef0af8a06a1eeec5bd2cc2956c8976b2c8809efde69df4a3a614b

ARG groupid=5000
ARG userid=5000

WORKDIR /app/

RUN groupadd -r kent && useradd --no-log-init -r -g kent kent

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tini && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install -U 'pip>=20' && \
    pip install --no-cache-dir 'kent==1.2.0'

USER kent

ENTRYPOINT ["tini", "--", "/usr/local/bin/kent-server"]
CMD ["run"]
