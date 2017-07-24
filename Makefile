.PHONY: build clean migrate redis-cache-cli redis-store-cli revision shell stop test run django-shell docs psql build-frontend

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
	@echo "  django-shell Django integrative shell"
	@echo "  psql         Open the psql cli"
	@echo "  build-frontend  Builds the frontend static files\n"

# Dev configuration steps
.docker-build:
	make build

.env:
	./bin/cp-env-file.sh

build: .env
	docker-compose build deploy-base
	docker-compose build dev-base
	touch .docker-build

clean: .env stop
	docker-compose rm -f
	rm -rf coverage/ .coverage
	rm -fr .docker-build

migrate: .env
	docker-compose run web python manage.py migrate --run-syncdb

shell: .env .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose run --user 0 web bash

currentshell: .env .docker-build
	# Use `-u 0` to automatically become root in the shell
	docker-compose exec --user 0 web bash

redis-cache-cli: .env .docker-build
	docker-compose run redis-cache redis-cli -h redis-cache

redis-store-cli: .env .docker-build
	docker-compose run redis-store redis-cli -h redis-store

psql: .env .docker-build
	docker-compose run db psql -h db -U postgres

stop: .env
	docker-compose stop

test: .env .docker-build
	@bin/test

run: .env .docker-build
	docker-compose up web worker frontend

gunicorn: .env .docker-build
	docker-compose run --service-ports web web

django-shell: .env .docker-build
	docker-compose run web python manage.py shell

docs: .env .docker-build
	docker-compose run -u 0 web ./bin/build_docs.sh

systemtest: .env .docker-build
	docker-compose run systemtest tests/systemtest/run_tests.sh

tag:
	@bin/make-tag.py

build-frontend:
	docker-compose run -u 0 web ./bin/build_frontend.sh
