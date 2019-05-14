#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

grr_on_prettier() {
    echo "
The above printed files weren't prettier enough.

To check a file use:
    prettier src/Home.js | diff src/Home.js -

To fix up a file use:
    prettier --write src/Home.js

To run 'prettier' inside the frontend Docker container run:

    docker-compose run frontend bash
    prettier --list-different src/*.js

Or, to just fix them:

    docker-compose run frontend bash
    prettier --write src/*.js

The config is defined in .prettierrc
Ideally configure your editor to automatically apply.
See https://prettier.io/docs/en/editors.html#content
"
    echo -n "Based on prettier version "
    /node_modules/.bin/prettier --version
    exit 1
}

case $1 in
  start)
    # The `| cat` is to trick Node that this is an non-TTY terminal
    # then react-scripts won't clear the console.
    yarn start | cat
    ;;
  lint)
    # The --list-different (alias -l) will error the execution if there
    # was a any files that came out different from what they should
    # be with the current configuration.
    /node_modules/.bin/prettier -l "src/**/*.js" || grr_on_prettier
    ;;
  lintfix)
    # Just Prettier format all the frontend files.
    /node_modules/.bin/prettier --write "src/**/*.js"
    ;;
  *)
    exec "$@"
    ;;
esac
