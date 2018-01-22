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
from django.utils import timezone
from django.db import OperationalError

from tecken.s3 import S3Bucket
from tecken.boto_extra import (
    reraise_clienterrors,
    reraise_endpointconnectionerrors
)
from tecken.base.utils import requests_retry_session
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.download.utils import store_missing_symbol
from tecken.upload.utils import upload_file_upload
from tecken.symbolicate.utils import invalidate_symbolicate_cache

logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


@shared_task(autoretry_for=(OperationalError,))
def store_missing_symbol_task(*args, **kwargs):
    """The store_missing_symbol() function is preferred to use directly
    because it can return a "hash". The hash is useful for doing
    Microsoft downloads where it wants to associate the missing download
    with the record of trying to find it on Microsoft's symbol server.

    Use this task when you are OK with doing a fire-and-forget of
    logging that the symbol is indeed missing.
    """
    store_missing_symbol(*args, **kwargs)


class DumpSymsError(Exception):
    """happens when dump_syms only spits something out on stderr"""


@shared_task(autoretry_for=(
    EndpointConnectionError,
    ConnectionError,
    ClientError,
))
@reraise_clienterrors
@reraise_endpointconnectionerrors
def download_microsoft_symbol(
    symbol,
    debugid,
    code_file=None,
    code_id=None,
    missing_symbol_hash=None
):
    MS_URL = 'https://msdl.microsoft.com/download/symbols/'
    MS_USER_AGENT = 'Microsoft-Symbol-Server/6.3.0.0'
    url = MS_URL + '/'.join([symbol, debugid, symbol[:-1] + '_'])
    session = requests_retry_session()
    response = session.get(url, headers={'User-Agent': MS_USER_AGENT})
    if response.status_code != 200:
        logger.info(
            f'Symbol {symbol}/{debugid} does not exist on msdl.microsoft.com'
        )
        return

    # The fact that the file does exist on Microsoft's server means
    # we're going to download it and at least look at it.
    if not missing_symbol_hash:
        missing_symbol_hash = store_missing_symbol(
            symbol,
            debugid,
            os.path.splitext(symbol)[0] + '.sym',
            code_file=code_file,
            code_id=code_id,
        )
    else:
        assert isinstance(missing_symbol_hash, str), missing_symbol_hash
    missing_symbol = MissingSymbol.objects.get(hash=missing_symbol_hash)
    download_obj = MicrosoftDownload.objects.create(
        missing_symbol=missing_symbol,
        url=url,
    )

    with tempfile.TemporaryDirectory() as tmpdirname:
        filepath = os.path.join(tmpdirname, os.path.basename(url))
        with open(filepath, 'wb') as f:
            content = response.content
            if not content.startswith(b'MSCF'):
                error_msg = (
                    f"Beginning of content in {url} did not start with 'MSCF'"
                )
                logger.info(error_msg)
                download_obj.error = error_msg
                download_obj.save()
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
        with metrics.timer('download_cabextract'):
            std_out, std_err = pipe.communicate()
            if std_err:
                error_msg = (
                    f'cabextract failed for {url}. Error: {std_err!r}'
                )
                logger.warning(error_msg)
                download_obj.error = error_msg
                download_obj.save()
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
        with metrics.timer('download_dump_syms'):
            std_out, std_err = pipe.communicate()
            # Note! It's expected, even if the dump_syms call works,
            # that the stderr contains something like:
            # b'Failed to find paired exe/dll file\n'
            # which is fine and can be ignored.
            if std_err and not std_out:
                error_msg = (
                    f'dump_syms extraction failed for {url}. '
                    f'Error: {std_err!r}'
                )
                download_obj.error = error_msg
                download_obj.save()
                raise DumpSymsError(error_msg)

        # Let's go ahead and upload it now, if it hasn't been uploaded
        # before.
        file_path = os.path.join(
            tmpdirname,
            os.path.splitext(os.path.basename(filepath))[0] + '.sym'
        )
        with open(file_path, 'wb') as f:
            f.write(std_out)
        upload_microsoft_symbol(
            symbol,
            debugid,
            file_path,
            download_obj,
        )


@metrics.timer('download_upload_microsoft_symbol')
def upload_microsoft_symbol(symbol, debugid, file_path, download_obj):
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
        file_path,
        microsoft_download=True,
    )

    # The _create_file_upload() function might return None
    # which means it decided there is no need to make an upload
    # of this specific file.
    if file_upload:
        download_obj.skipped = False
        download_obj.file_upload = file_upload
        metrics.incr('download_microsoft_download_file_upload_upload', 1)
    else:
        download_obj.skipped = True
        logger.info(f'Skipped key {key_name}')
        metrics.incr('download_microsoft_download_file_upload_skip', 1)
    download_obj.completed_at = timezone.now()
    download_obj.save()

    # We need to inform the symbolicate app, that some new symbols
    # were uploaded.
    symbol_key = (symbol, debugid)
    invalidate_symbolicate_cache([symbol_key])
