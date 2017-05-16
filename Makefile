.PHONY: build clean migrate redis-cache-cli redis-store-cli revision shell stop test run django-shell docs

help:
	@echo "Welcome to the tecken\n"
	@echo "The list of commands for local development:\n"
	@echo "  build        Builds the docker images for the docker-compose setup"
	@echo "  ci           Run the test with the CI specific Docker setup"
	@echo "  clean        Stops and removes all docker containers"
	@echo "  migrate      Runs the Django database migrations"
	@echo "  redis-cache-cli  Opens a Redis CLI to the cache Redis server"
	@echo "  redis-store-cli  Opens a Redis CLI to the store Redis server"
	@echo "  shell        Opens a Bash shell"
	@echo "  test         Runs the Python test suite"
	@echo "  run          Runs the whole stack, served on http://localhost:8000/"
	@echo "  gunicorn     Runs the whole stack using gunicorn on http://localhost:8000/"
	@echo "  stop         Stops the docker containers"
	@echo "  systemtest   Run system tests against a running tecken"
	@echo "  django-shell Django integrative shell\n"

# Dev configuration steps
.docker-build:
	make build

build:
	docker-compose build deploy-base
	docker-compose build dev-base
	touch .docker-build

clean: stop
	docker-compose rm -f
	rm -rf coverage/ .coverage
	rm -fr .docker-build

migrate:
	docker-compose run web python manage.py migrate --run-syncdb

shell: .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose run --user 0 web bash

currentshell: .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose exec --user 0 web bash

redis-cache-cli: .docker-build
	docker-compose run redis-cache redis-cli -h redis-cache

redis-store-cli: .docker-build
	docker-compose run redis-store redis-cli -h redis-store

stop:
	docker-compose stop

test: .docker-build
	@bin/test

run: .docker-build
	docker-compose up web worker

gunicorn: .docker-build
	docker-compose run --service-ports web web

django-shell: .docker-build
	docker-compose run web python manage.py shell

docs: .docker-build
	docker-compose run -u 0 web ./bin/build_docs.sh

systemtest: .docker-build
	docker-compose run systemtest tests/systemtest/run_tests.sh

tag:
	@bin/make-tag.py
