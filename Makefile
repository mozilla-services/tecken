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

.DEFAULT_GOAL := help
.PHONY: help
help:
	@echo "Usage: make RULE"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' Makefile \
		| grep -v grep \
	    | sed -n 's/^\(.*\): \(.*\)##\(.*\)/\1\3/p' \
	    | column -t  -s '|'
	@echo ""
	@echo "Adjust your .env file to set configuration."
	@echo ""
	@echo "See https://tecken.readthedocs.io/ for more documentation."

# Dev configuration steps
.docker-build:
	make build

.env:
	./bin/cp-env-file.sh

.PHONY: build
build: .env  ## | Build docker images.
	docker-compose build --build-arg userid=${USE_UID} --build-arg groupid=${USE_GID} base frontend linting
	touch .docker-build

.PHONY: setup
setup: .env  ## | Initialize services.
	docker-compose run --rm web /app/bin/setup-services.sh

.PHONY: run
run: .env .docker-build  ## | Run the web app and services.
	docker-compose up web worker frontend

.PHONY: stop
stop: .env  ## | Stop docker containers.
	docker-compose stop

.PHONY: shell
shell: .env .docker-build  ## | Open a shell in web container.
	docker-compose run --rm web bash

.PHONY: clean
clean: .env stop  ## | Stop and remove docker containers and artifacts.
	docker-compose rm -f
	rm -fr .docker-build
	rm -rf frontend/build/

.PHONY: clear-caches
clear-caches:  ## | Clear Redis caches.
	docker-compose run --rm redis-cache redis-cli -h redis-cache FLUSHDB
	docker-compose run --rm redis-store redis-cli -h redis-store FLUSHDB

.PHONY: redis-cache-cli
redis-cache-cli: .env .docker-build  ## | Open Redis CLI to cache Redis server.
	docker-compose run --rm redis-cache redis-cli -h redis-cache

.PHONY: redis-store-cli
redis-store-cli: .env .docker-build  ## | Open Redis CLI to store Redis server.
	docker-compose run --rm redis-store redis-cli -h redis-store

.PHONY: psql
psql: .env .docker-build  ## | Open psql cli.
	@echo "Password is 'postgres'."
	docker-compose run --rm db psql -h db -U postgres

.PHONY: test
test: .env .docker-build  ## | Run Python unit test suite.
	bin/test.sh

.PHONY: testshell
testshell: .env .docker-build  ## | Open shell in test environment.
	bin/test.sh --shell

.PHONY: docs
docs: .env .docker-build  ## | Build docs.
	docker-compose run --rm --user ${USE_UID} linting docs

.PHONY: lint
lint: .env .docker-build  ## | Lint code.
	docker-compose run --rm linting lint
	docker-compose run --rm frontend lint

.PHONY: lintfix
lintfix: .env .docker-build  ## | Reformat code.
	docker-compose run --rm linting lintfix
	docker-compose run --rm frontend lintfix
