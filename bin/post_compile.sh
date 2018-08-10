#!/bin/bash -e
# Tasks run by the Heroku Python buildpack after the compile step.

# The post_compile script is run in a sub-shell, so we need to source the
# buildpack's utils script again, so we can use set-env/set-default-env:
# https://github.com/heroku/heroku-buildpack-python/blob/master/bin/utils
source $BIN_DIR/utils

# Override the hostname that is displayed in New Relic, so the Dyno name
# (eg "web.1") is shown, rather than "Dynamic Hostname". $DYNO is quoted
# so that it's expanded at runtime on each dyno, rather than now.
set-env NEW_RELIC_PROCESS_HOST_DISPLAY_NAME '$DYNO'
