#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import print_function  # in case you use Python 2

import datetime
import subprocess

try:
    input = raw_input
except NameError:
    # good, you're using Python 3
    pass


def run():
    # Let's make sure we're up-to-date
    current_branch = subprocess.check_output(
        'git rev-parse --abbrev-ref HEAD'.split()
    ).strip()
    if current_branch != 'master':
        print("Must be on the master branch to do this")
        return 1

    # The current branch can't be dirty
    try:
        subprocess.check_call(
            'git diff --quiet --ignore-submodules HEAD'.split()
        )
    except subprocess.CalledProcessError:
        print(
            "Can't be \"git dirty\" when we're about to git pull. "
            "Stash or commit what you're working on."
        )
        return 2

    # Make sure we have all the old git tags
    subprocess.check_output(
        'git pull origin master --tags'.split(),
        stderr=subprocess.STDOUT
    )

    # We're going to use the last tag to help you write a tag message
    last_tag, last_tag_message = subprocess.check_output([
        'git',
        'for-each-ref',
        '--sort=-taggerdate',
        '--count=1',
        '--format',
        '%(tag)|%(contents:subject)',
        'refs/tags'
    ]).strip().split('|', 1)

    print('\nLast tags was: {}'.format(last_tag))
    if last_tag_message.count('\n') > 1:
        print('Message:')
        print(last_tag_message)
    else:
        print('Message: ', last_tag_message)
    print('-' * 80)

    commits_since = subprocess.check_output(
        'git log {last_tag}..HEAD --oneline'.format(last_tag=last_tag).split()
    )
    print('Commits since last tag:')
    for commit in commits_since.splitlines():
        print('\t', commit)
    print('-' * 80)

    # Next, come up with the next tag name.
    # Normally it's today's date in ISO format with dots.
    tag_name = datetime.datetime.utcnow().strftime('%Y.%m.%d')
    # But is it taken, if so how many times has it been taken before?
    existing_tags = subprocess.check_output([
        'git', 'tag', '-l', '{}*'.format(tag_name)
    ]).strip().splitlines()
    if existing_tags:
        count_starts = len(
            [x for x in existing_tags if x.startswith(tag_name)]
        )
        tag_name += '-{}'.format(count_starts + 1)

    # Now we need to figure out what's been
    message = input("Tag message? (Optional, else all commit messages) ")
    if not message:
        message = commits_since

    # Now we can create the tag
    subprocess.check_call([
        'git',
        'tag',
        '-a', tag_name,
        '-m', message
    ])

    # Let's push this now
    subprocess.check_call(
        'git push origin master --tags'.split()
    )


if __name__ == '__main__':
    import sys
    sys.exit(run())
