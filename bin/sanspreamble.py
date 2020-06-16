#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import fnmatch
import subprocess
import sys


def main():
    exceptions = (
        ".*",
        "docs/conf.py",
        "registerServiceWorker.js",
    )

    alreadies = subprocess.check_output(
        [
            "git",
            "grep",
            "-l",
            "This Source Code Form is subject to the terms of the Mozilla Public",
        ]
    )
    alreadies = alreadies.decode("utf-8").splitlines()

    out = subprocess.check_output(["git", "ls-files"])
    out = out.decode("utf-8").splitlines()

    suspect = []
    for fp in out:
        if fp in alreadies:
            continue
        if [x for x in exceptions if fnmatch.fnmatch(fp, x)]:
            continue
        if fp.endswith((".sh", ".py", ".js")):
            suspect.append(fp)

    for i, fp in enumerate(suspect):
        if not i:
            print("The following appear to lack a license preamble:".upper())
        print(fp)

    return bool(suspect)


if __name__ == "__main__":
    sys.exit(main())
