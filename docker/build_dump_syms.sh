#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Failures should cause setup to fail
set -v -e -x

git clone --recurse-submodules https://github.com/luser/dump_syms.git
cd dump_syms

export CXX="g++-4.8" CC="gcc-4.8"

CXXFLAGS=-O2 gyp -f ninja --depth=. ./dump_syms.gyp
ninja -C out/Default

ls -l out/Default

# Put the final binaries in /stackwalk in the container
mkdir -p /dump_syms
cp out/Default/dump_syms /dump_syms/
