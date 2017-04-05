tecken - All things Mozilla Symbol Server
=========================================

[![Updates](https://pyup.io/repos/github/mozilla/tecken/shield.svg)](https://pyup.io/repos/github/mozilla/tecken/)

Development Setup
-----------------

This application uses Docker for local development. Please make sure to
[install Docker](https://docs.docker.com/mac/) and
[Docker Compose](https://docs.docker.com/compose/install/).

To set the application up, please copy the `.env-dist` file to one named `.env`
and then update the variables starting with `AWS_` with the appropriate.

Set the `DJANGO_SECRET_KEY` variable using the output of the following command:

    python -c "from django.utils.crypto import get_random_string; print(get_random_string(50))"

To start the application, run `make up`.

Quick troubleshooting guide:

* Docker gives an error message similar to `ERROR: Couldn't connect to Docker daemon at http+docker://localunixsocket - is it running?`
    * Run the command as administrator/superuser (for testing purposes, that is).
    * Make sure the user is in the `docker` group (use the `sudo usermod -aG docker ${USER}` command to do this). This allows the user to use Docker without superuser privileges. Note that this does not take effect until the user logs out and logs in again.

* Docker-Compose gives an error message similar to `ERROR: client and server don't have same version (client : 1.21, server: 1.18)`
    * Make sure to install the latest versions of both Docker and Docker-Compose. The current versions of these in the Debian repositories might not be mutually compatible.

* Docker gives an error message similar to `Err http://security.debian.org jessie/updates InRelease`
    * The installed Docker version is possibly too old. Make sure to use the latest available stable version.
    * Ensure that the DNS configuration is sane: see if `docker-compose run web ping security.debian.org` can connect successfully.

* Django gives an error message similar to `OperationalError: SOME_TABLE doesn't exist`
    * The database likely isn't set up correctly.
    * Run `make migrate` to update it.

* Django gives some other form of `OperationalError`, and we don't really care about the data that's already in the database (e.g., while developing or testing)
    * Most database issues can be resolved by just deleting the database, `telemetry_analysis.db`. It will be recreated on the next run.

* Database errors are usually caused by an improper database configuration. For development purposes, recreating the database will often solve the issue.

* Django gives an error message similar to `'NoneType' object has no attribute 'get_frozen_credentials'`.
    * The AWS credentials on the current machine are likely not correctly set.
    * Set them in your **ENVIRONMENT VARIABLES** (these environment variables are transferred to the docker container, from definitions in `.env`).
    * See the [relevant section of the Boto3 docs](https://boto3.readthedocs.org/en/latest/guide/configuration.html#environment-variables) for more details.


Python dependencies
-------------------

Python dependencies are installed using pip during the Docker image build
process. As soon as you build the docker image using `make build` it'll
check if the `requirements.txt` file has changed and rebuilds the container
image if needed.

To add a new Python dependency please:

* Add it to the `requirements.txt` file, including a hash for pip's
  [hash checking mode](https://pip.pypa.io/en/stable/reference/pip_install/#hash-checking-mode).
* Run `make build` on the host machine.

That will rebuild the images used by docker-compose.

Front-end dependencies
----------------------

The front-end dependencies are installed when building the Docker images
just like Python dependencies.

To add a new dependency:

* Add it to the `packages.json` file
* Run `make build` on the host machine
* Extend the `NPM_FILE_PATTERNS` setting in the `settings.py`
  file with the files that are needed to be copied by Django's
  `collectstatic` management command.

That will rebuild the images used by docker-compose.

Run the tests
-------------

There's a sample test in `tests/test_users.py` for your convenience,
that you can run using the following command on your computer:

    make test

This will spin up a Docker container to run the tests, so please set up
the development setup first.
