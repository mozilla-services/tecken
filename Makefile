.PHONY: build clean migrate redis-cache-cli redis-store-cli revision shell stop test up django-shell

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
	@echo "  up           Runs the whole stack, served under http://localhost:8000/"
	@echo "  stop         Stops the docker containers"
	@echo "  django-shell Django integrative shell\n"

build:
	docker-compose build

clean: stop
	docker-compose rm -f
	rm -rf coverage/ .coverage

migrate:
	docker-compose run web python manage.py migrate --run-syncdb

shell:
	# Use `-u 0` to automatically become root in the shell
	docker-compose run -u 0 web bash

redis-cache-cli:
	docker-compose run redis-cache redis-cli -h redis-cache

redis-store-cli:
	docker-compose run redis-store redis-cli -h redis-store

stop:
	docker-compose stop

test:
	@bin/test

up:
	docker-compose up

django-shell:
	docker-compose run web python manage.py shell
