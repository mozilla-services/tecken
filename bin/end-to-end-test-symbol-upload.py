#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import time

import requests

STAGE_BASE = 'https://symbols.stage.mozaws.net'
PROD_BASE = 'https://symbols.mozilla.org'


def run(prod_token, stage_token):
    r = requests.get(STAGE_BASE + '/api/_auth/', headers={
        'auth-token': stage_token
    })
    r.raise_for_status()
    stage_user = r.json()['user']
    print("Stage user:", stage_user['email'])

    r = requests.get(PROD_BASE + '/api/_auth/', headers={
        'auth-token': prod_token
    })
    r.raise_for_status()
    prod_user = r.json()['user']
    print("Prod user:", prod_user['email'])

    url = PROD_BASE + '/api/uploads/'
    r = requests.get(url, headers={
        'auth-token': prod_token,
    })
    r.raise_for_status()
    uploads = r.json()['uploads']
    for upload in uploads:
        if upload['download_url']:
            break
    else:
        raise NotImplementedError("None with download_url!")

    print("About to upload", fmtsize(upload['size']), 'as URL to Stage.')
    t0 = time.time()
    r = requests.post(
        STAGE_BASE + '/upload/',
        data={
            'url': upload['download_url'],
        },
        headers={
            'auth-token': stage_token,
        }
    )
    t1 = time.time()
    r.raise_for_status()
    uploaded = r.json()['upload']
    print()
    # from pprint import pprint
    # pprint(uploaded)
    print("Took", fmtsecs(t1 - t0))

    id = uploaded['id']
    url = STAGE_BASE + '/api/uploads/upload/{}'.format(id)
    r = requests.get(url, headers={'auth-token': stage_token})
    r.raise_for_status()
    upload = r.json()['upload']
    print('Files skipped:', len(upload['skipped_keys']))
    print('Files uploaded:', len(upload['file_uploads']))
    print('Files uploaded, completed:', len(
        [x for x in upload['file_uploads'] if x['completed_at']]
    ))
    print()
    url = STAGE_BASE + '/uploads/upload/{}'.format(id)
    print("To see it, go to:", url)
    print()
    print('It worked! 🎉 🎊 👍🏼 🌈')


def fmtsize(b):
    kb = b / 1024
    mb = kb / 1024
    gb = mb / 1024
    if gb > 1:
        return f'{gb:.1f}GB'
    elif mb > 1:
        return f'{mb:.1f}MB'
    return f'{kb:.1f}KB'


def fmtsecs(seconds):
    minutes = seconds / 60
    if minutes > 60:
        hours = minutes / 60
        return f'{hours:.1f} hours'
    elif minutes > 1:
        return f'{minutes:.1f} minutes'
    return f'{seconds:.1f} seconds'


def main():
    import argparse
    parser = argparse.ArgumentParser(description=(
        "Requires two API tokens. One for Prod (for viewing Uploads) and "
        "one for Stage (for uploading Uploads).\nThen it takes one the most "
        "recent upload from Prod that has a download_url and sends that to "
        "stage."
    ))
    parser.add_argument(
        'prod_token',
    )
    parser.add_argument(
        'stage_token',
    )
    args = parser.parse_args()
    return run(
        args.prod_token,
        args.stage_token,
    )


if __name__ == '__main__':
    import sys
    sys.exit(main())
