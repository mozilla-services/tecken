# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Include my.env and export it so variables set in there are available
# in the Makefile.
include .env
export

# Set these in the environment to override them. This is helpful for
# development if you have file ownership problems because the user
# in the container doesn't match the user on your host.
USE_UID ?= 10001
USE_GID ?= 10001

.PHONY: help
help: default

.PHONY: default
default:
	@echo "Welcome to the tecken\n"
	@echo "The list of commands for local development:\n"
	@echo "  build            Builds the docker images for the docker-compose setup"
	@echo "  setup            Initializes services"
	@echo "  run              Runs the whole stack, served on http://localhost:8000/"
	@echo "  stop             Stops the docker containers"
	@echo ""
	@echo "  clean            Stops and removes all docker containers"
	@echo "  redis-cache-cli  Opens a Redis CLI to the cache Redis server"
	@echo "  redis-store-cli  Opens a Redis CLI to the store Redis server"
	@echo "  clear-caches     Clear Redis caches"
	@echo "  shell            Opens a Bash shell"
	@echo "  test             Runs the Python test suite"
	@echo "  testshell        Runs a shell in the test environment"
	@echo "  psql             Open the psql cli"
	@echo "  lint             Lint code"
	@echo "  lintfix          Reformat code"
	@echo "  build-frontend   Builds the frontend static files\n"

# Dev configuration steps
.docker-build:
	make build

.env:
	./bin/cp-env-file.sh

.PHONY: build
build: .env
	docker-compose build --build-arg userid=${USE_UID} --build-arg groupid=${USE_GID} base frontend linting
	touch .docker-build

.PHONY: clean
clean: .env stop
	docker-compose rm -f
	rm -rf coverage/ .coverage
	rm -fr .docker-build

.PHONY: clear-caches
clear-caches:
	docker-compose run --rm redis-cache redis-cli -h redis-cache FLUSHDB
	docker-compose run --rm redis-store redis-cli -h redis-store FLUSHDB

.PHONY: setup
setup: .env
	docker-compose run --rm web /app/bin/setup-services.sh

.PHONY: shell
shell: .env .docker-build
	docker-compose run --rm web bash

.PHONY: redis-cache-cli
redis-cache-cli: .env .docker-build
	docker-compose run redis-cache redis-cli -h redis-cache

.PHONY: redis-store-cli
redis-store-cli: .env .docker-build
	docker-compose run redis-store redis-cli -h redis-store

.PHONY: psql
psql: .env .docker-build
	@echo "Password is 'postgres'."
	docker-compose run db psql -h db -U postgres

.PHONY: stop
stop: .env
	docker-compose stop

.PHONY: test
test: .env .docker-build frontend/build/
	bin/test.sh

.PHONY: testshell
testshell: .env .docker-build
	bin/test.sh --shell

.PHONY: run
run: .env .docker-build
	docker-compose up web worker frontend

.PHONY: docs
docs:
	bin/build-docs-locally.sh

frontend/build/:
	make build-frontend

.PHONY: build-frontend
build-frontend:
	docker-compose run -e CI web ./bin/build_frontend.sh

.PHONY: lint
lint: .env .docker-build
	docker-compose run linting lint
	docker-compose run frontend lint

.PHONY: lintfix
lintfix: .env .docker-build
	docker-compose run linting lintfix
	docker-compose run frontend lintfix
