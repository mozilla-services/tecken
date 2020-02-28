# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

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
	@echo "  currentshell     Opens a Bash shell into existing running 'web' container"
	@echo "  test             Runs the Python test suite"
	@echo "  testshell        Runs a shell in the test environment"
	@echo "  gunicorn         Runs the whole stack using gunicorn on http://localhost:8000/"
	@echo "  django-shell     Django integrative shell"
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
	docker-compose build base
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
	docker-compose run web /app/bin/setup-services.sh

.PHONY: shell
shell: .env .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose run --user 0 web bash

.PHONY: currentshell
currentshell: .env .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose exec --user 0 web bash

.PHONY: redis-cache-cli
redis-cache-cli: .env .docker-build
	docker-compose run redis-cache redis-cli -h redis-cache

.PHONY: redis-store-cli
redis-store-cli: .env .docker-build
	docker-compose run redis-store redis-cli -h redis-store

.PHONY: psql
psql: .env .docker-build
	docker-compose run db psql -h db -U postgres

.PHONY: stop
stop: .env
	docker-compose stop

.PHONY: test
test: .env .docker-build
	@bin/test.sh

.PHONY: testshell
testshell: .env .docker-build
	@bin/test.sh --shell

.PHONY: run
run: .env .docker-build
	docker-compose up web worker frontend

.PHONY: gunicorn
gunicorn: .env .docker-build
	docker-compose run --service-ports web web

.PHONY: django-shell
django-shell: .env .docker-build
	docker-compose run web python manage.py shell

.PHONY: docs
docs:
	@bin/build-docs-locally.sh

.PHONY: build-frontend
build-frontend:
	docker-compose run -u 0 -e CI base ./bin/build_frontend.sh

.PHONY: link
lint: .env .docker-build
	docker-compose run linting lint
	docker-compose run frontend lint

.PHONY: lintfix
lintfix: .env .docker-build
	docker-compose run linting lintfix
	docker-compose run frontend lintfix
