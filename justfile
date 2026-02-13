# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

_default:
    @just --list

_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
      echo "Copying docker/config/env-dist to .env..."
      ./bin/cp-dist-file.sh docker/config/env-dist .env
    fi


SERVICES := "db redis-cache localstack statsd oidcprovider gcs-emulator"

# Create a slick.sh file
slick-sh:
    ./bin/cp-dist-file.sh docker/config/slick.sh-dist slick.sh
    chmod 755 slick.sh

# Build docker images.
build *args='base frontend fakesentry db redis-cache localstack statsd oidcprovider gcs-emulator': _env
    docker compose --progress plain build {{args}}

# Set up services.
setup: _env
    docker compose run --rm web bash ./bin/setup-services.sh

# Run webapp and services.
run *args='--attach web --attach frontend --attach fakesentry web frontend fakesentry': _env
    docker compose up {{args}}

# Stop service containers.
stop *args: _env
    docker compose stop {{args}}

# Remove service containers and networks.
down *args: _env
    docker compose down {{args}}

# Open a shell in the web image.
shell *args='/bin/bash': _env
    docker compose run --rm --entrypoint= web {{args}}

# Open a shell in the test container.
test-shell *args='/bin/bash': _env
    docker compose run --rm --entrypoint= test {{args}}

# Stop and remove docker containers and artifacts.
clean: _env stop
    docker compose rm -f
    rm -fr .docker-build
    rm -rf frontend/build/
    git restore frontend/build/

# Lint code, or use --fix to reformat Python code and apply auto-fixes for lint.
lint *args: _env
	docker compose run --rm --no-deps test bash ./bin/run_lint.sh {{args}}
	docker compose run --rm frontend lint

# Run Python unit test suite.
test *args: _env
    docker compose run --rm test bash ./bin/run_test.sh {{args}}

# Build docs.
docs: _env
    docker compose run --rm --no-deps web bash make -C docs/ clean
    docker compose run --rm --no-deps web bash make -C docs/ html

# Run uv inside the container
uv *args: _env
	docker compose run --rm --no-deps web bash uv {{args}}

# Check how far behind different server environments are from main tip.
service-status *args: _env
    docker compose run --rm --no-deps web bash service-status {{args}}

# Open psql cli.
psql *args: _env
    @echo "\e[0;32mNOTE: Use password 'postgres'.\e[0m\n"
    docker compose run --rm db psql -h db -U postgres -d tecken

# Clear Redis cache.
clear-cache: _env
    docker compose run --rm redis-cache redis-cli -h redis-cache FLUSHDB

# Redis cli.
redis-cache-cli: _env
    docker compose run --rm redis-cache redis-cli -h redis-cache
