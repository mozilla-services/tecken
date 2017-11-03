#!/usr/bin/env bash
set -eo pipefail

grr_on_prettier() {
    echo "
The above printed files weren't prettier enough.

To check a file use:
    ./node_modules/.bin/prettier src/Home.js | diff src/Home.js -

To fix up a file use:
    ./node_modules/.bin/prettier --write src/Home.js

The config is defined in .prettierrc
Ideally configure your editor to automatically apply.
See https://prettier.io/docs/en/editors.html#content
"
    return 1
}

case $1 in
  start)
    # The `| cat` is to trick Node that this is an non-TTY terminal
    # then react-scripts won't clear the console.
    yarn start | cat
    ;;
  lint)
    # The options are in the .prettierrc file.
    # The --list-different (alias -l) will error the execution if there
    # was a any files that came out different from what they should
    # be with the current configuration.
    /node_modules/.bin/prettier -l "src/**/*.js" || grr_on_prettier
    ;;
  *)
    exec "$@"
    ;;
esac
