# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import tempfile
import subprocess
import logging

import markus
from celery import shared_task
from botocore.exceptions import (
    EndpointConnectionError,
    ConnectionError,
    ClientError,
)

from django.conf import settings

from tecken.s3 import S3Bucket
from tecken.boto_extra import (
    reraise_clienterrors,
    reraise_endpointconnectionerrors
)
from tecken.base.utils import requests_retry_session
from tecken.upload.tasks import upload_file_upload


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


class DumpSymsError(Exception):
    """happens when dump_syms only spits something out on stderr"""


@shared_task(autoretry_for=(
    EndpointConnectionError,
    ConnectionError,
    ClientError,
))
@reraise_clienterrors
@reraise_endpointconnectionerrors
def download_microsoft_symbol(symbol, debugid, code_file=None, code_id=None):
    MS_URL = 'https://msdl.microsoft.com/download/symbols/'
    MS_USER_AGENT = 'Microsoft-Symbol-Server/6.3.0.0'
    debug_file = symbol
    url = MS_URL + '/'.join([debug_file, debugid, debug_file[:-1] + '_'])
    session = requests_retry_session()
    r = session.get(url, headers={'User-Agent': MS_USER_AGENT})
    if r.status_code != 200:
        logger.debug(
            f'Symbol {debug_file}/{debugid} does not '
            'exist on msdl.microsoft.com'
        )
        return

    with tempfile.TemporaryDirectory() as tmpdirname:
        filepath = os.path.join(tmpdirname, os.path.basename(url))
        with open(filepath, 'wb') as f:
            content = r.content
            if not content.startswith(b'MSCF'):
                logger.info(
                    f"Beginning of content in {url} did not start with 'MSCF'"
                )
                return
            f.write(content)

        cmd = [
            settings.CABEXTRACT_PATH,
            '--quiet',
            # Important so that the extract .pdb filename is predictable.
            '--lowercase',
            '--directory', tmpdirname,
            filepath,
        ]
        logger.debug(' '.join(cmd))
        pipe = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        with metrics.timer('cabextract'):
            std_out, std_err = pipe.communicate()
            if std_err:
                logger.warning(
                    f'cabextract failed for {url}. Error: {std_err!r}'
                )
                return

        # Running cabextract creates a file 'foo.pdb' from 'foo.pd_'
        pdb_filepath = filepath.lower().replace('.pd_', '.pdb')
        assert pdb_filepath != filepath
        assert os.path.isfile(pdb_filepath), pdb_filepath
        cmd = [
            settings.DUMP_SYMS_PATH,
            pdb_filepath,
        ]
        logger.debug(' '.join(cmd))
        pipe = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        with metrics.timer('dump_syms'):
            std_out, std_err = pipe.communicate()
            # Note! It's expected, even if the dump_syms call works,
            # that the stderr contains something like:
            # b'Failed to find paired exe/dll file\n'
            # which is fine and can be ignored.
            if std_err and not std_out:
                raise DumpSymsError(
                    f'dump_syms extraction failed for {url}. '
                    f'Error: {std_err!r}'
                )

        # Let's go ahead and upload it now, if it hasn't been uploaded
        # before.
        upload_microsoft_symbol(symbol, debugid, std_out)


@metrics.timer('upload_microsoft_symbol')
def upload_microsoft_symbol(symbol, debugid, content):
    filename = os.path.splitext(symbol)[0]
    uri = f'{symbol}/{debugid}/{filename}.sym'
    key_name = os.path.join(settings.SYMBOL_FILE_PREFIX, uri)

    bucket_info = S3Bucket(settings.UPLOAD_DEFAULT_URL)
    s3_client = bucket_info.s3_client
    bucket_name = bucket_info.name

    # The upload_file_upload creates an instance but doesn't save it
    file_upload = upload_file_upload(
        s3_client,
        bucket_name,
        key_name,
        content,
    )
    if file_upload:
        file_upload.microsoft_download = True
        # Remember, upload_file_upload() doesn't save. Just creates instances.
        file_upload.save()

    # The _create_file_upload() function might return None
    # which means it decided there is no need to make an upload
    # of this specific file.
    if file_upload:
        logger.info(f'Uploaded key {key_name}')
        metrics.incr('microsoft_download_file_upload_upload', 1)
    else:
        logger.info(f'Skipped key {key_name}')
        metrics.incr('microsoft_download_file_upload_skip', 1)
