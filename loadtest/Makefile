# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

HERE = $(shell pwd)
PYTHON = python3
BIN = $(HERE)/venv/bin
VENV_PIP = $(BIN)/pip3
VENV_PYTHON = $(BIN)/python
VENV_INSTALL = $(VENV_PIP) install
STACKSDIR = $(HERE)/stacks

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
	@echo "Read README.rst for more details."

.venv-build:
	make build

.PHONY: build
build:  ## | Build virtual environment
	-rm -rf $(HERE)/venv
	$(PYTHON) -m venv $(HERE)/venv
	$(VENV_INSTALL) -r requirements.txt
	touch .venv-build

.PHONY: buildstacks
buildstacks: .venv-build  ## | Build stacks to loadtest with
	-mkdir $(STACKSDIR)
	$(VENV_PYTHON) ../systemtests/bin/fetch-crashids.py --num-results=100 | $(VENV_PYTHON) ../systemtests/bin/make-stacks.py save $(STACKSDIR)
	@echo "`ls $(STACKSDIR)/*.json | wc -l` stacks total."

.PHONY: size
size: .venv-build  ## | Run molotov in sizing mode
	$(BIN)/molotov --sizing loadtest.py

.PHONY: smoketest
smoketest: .venv-build  ## | Run a smoketest
	$(BIN)/molotov --workers=1 --processes=1 -d 10 loadtest.py

.PHONY: loadtest
loadtest: .venv-build  ## | Run a loadtest
	$(BIN)/molotov --workers=5 --processes=5 -d 600 loadtest.py
