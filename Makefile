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

DOCKER := $(shell which docker)
DC=${DOCKER} compose

SERVICES=db fakesentry redis-cache localstack statsd oidcprovider

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
	./bin/cp-dist-file.sh docker/config/env-dist .env

slick.sh:
	./bin/cp-dist-file.sh docker/config/slick.sh-dist slick.sh
	chmod 755 slick.sh

.PHONY: build
build: .env  ## | Build docker images.
	${DC} build --build-arg userid=${USE_UID} --build-arg groupid=${USE_GID} --progress plain base frontend
	${DC} build --progress plain fakesentry ${SERVICES}
	touch .docker-build

.PHONY: setup
setup: .env  ## | Initialize services.
	${DC} run --rm web bash /app/bin/setup-services.sh

.PHONY: run
run: .env .docker-build  ## | Run the web app and services.
	${DC} up web frontend fakesentry

.PHONY: stop
stop: .env  ## | Stop docker containers.
	${DC} stop

.PHONY: shell
shell: .env .docker-build  ## | Open a shell in web container.
	${DC} run --rm web bash

.PHONY: clean
clean: .env stop  ## | Stop and remove docker containers and artifacts.
	${DC} rm -f
	rm -fr .docker-build
	rm -rf frontend/build/
	git restore frontend/build/

.PHONY: clear-cache
clear-cache:  ## | Clear Redis cache.
	${DC} run --rm redis-cache redis-cli -h redis-cache FLUSHDB

.PHONY: redis-cache-cli
redis-cache-cli: .env .docker-build  ## | Open Redis CLI to cache Redis server.
	${DC} run --rm redis-cache redis-cli -h redis-cache

.PHONY: psql
psql: .env .docker-build  ## | Open psql cli.
	@echo "NOTE: Password is 'postgres'."
	${DC} run --rm db psql -h db -U postgres -d tecken

.PHONY: test
test: .env .docker-build  ## | Run Python unit test suite.
	${DC} up --detach ${SERVICES}
	${DC} run --rm test bash ./bin/run_test.sh

.PHONY: testshell
testshell: .env .docker-build  ## | Open shell in test environment.
	${DC} up --detach ${SERVICES}
	${DC} run --rm test bash ./bin/run_test.sh --shell

.PHONY: docs
docs: .env .docker-build  ## | Build docs.
	${DC} run --rm --user ${USE_UID} --no-deps web bash make -C docs/ clean
	${DC} run --rm --user ${USE_UID} --no-deps web bash make -C docs/ html

.PHONY: lint
lint: .env .docker-build  ## | Lint code.
	${DC} run --rm --no-deps test bash ./bin/run_lint.sh
	${DC} run --rm frontend lint

.PHONY: lintfix
lintfix: .env .docker-build  ## | Reformat code.
	${DC} run --rm --no-deps test bash ./bin/run_lint.sh --fix
	${DC} run --rm frontend lintfix

.PHONY: rebuildreqs
rebuildreqs: .env .docker-build  ## | Rebuild requirements.txt file after requirements.in changes.
	${DC} run --rm --no-deps web bash pip-compile --generate-hashes

.PHONY: updatereqs
updatereqs: .env .docker-build  ## | Update deps in requirements.txt file.
	${DC} run --rm --no-deps web bash pip-compile --generate-hashes -U
