.PHONY: build clean migrate redis-cli revision shell stop test up

help:
	@echo "Welcome to the tecken\n"
	@echo "The list of commands for local development:\n"
	@echo "  build      Builds the docker images for the docker-compose setup"
	@echo "  ci         Run the test with the CI specific Docker setup"
	@echo "  clean      Stops and removes all docker containers"
	@echo "  migrate    Runs the Django database migrations"
	@echo "  redis-cli  Opens a Redis CLI"
	@echo "  shell      Opens a Bash shell"
	@echo "  test       Runs the Python test suite"
	@echo "  up         Runs the whole stack, served under http://localhost:8000/\n"
	@echo "  stop       Stops the docker containers"

build:
	docker-compose build

clean: stop
	docker-compose rm -f
	rm -rf coverage/ .coverage

migrate:
	docker-compose run web python manage.py migrate --run-syncdb

shell:
	docker-compose run web bash

redis-cli:
	docker-compose run redis redis-cli -h redis

stop:
	docker-compose stop

test:
	@bin/test

up:
	docker-compose up
