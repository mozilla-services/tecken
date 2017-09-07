# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import time
import logging
import statistics

import markus

from django import http
from django.conf import settings
from django.utils.encoding import force_bytes
from django.core.cache import caches

from tecken.s3 import S3Bucket
from . import forms


logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


def caching_vs_boto(request):
    """
    This benchmarking function intends to measure how long it takes to

    1. Do a boto3 query to ask if a key exists
    2. Do a local memcache query to ask if a cache key exists
    3. Do a central Redis query to ask if a cache key exists

    """
    if (
        not settings.BENCHMARKING_ENABLED and
        not request.user.is_superuser
    ):
        return http.JsonResponse(
            {'error': 'benchmarking disabled'},
            status=403,
        )

    form = forms.CachingVsBotoForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    # Benchmarking parameters.
    iterations = form.cleaned_data['iterations']
    symbol_path = form.cleaned_data['symbol_path']

    # Setting up for boto lookup.
    s3_key = f'{settings.SYMBOL_FILE_PREFIX}/{symbol_path}'
    s3_info = S3Bucket(settings.SYMBOL_URLS[0])
    s3_client = s3_info.s3_client
    bucket_name = s3_info.name

    def lookup_boto(key):
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=key,
        )
        for obj in response.get('Contents', []):
            if obj['Key'] == key:
                # It exists!
                return True
        return False

    context = {}

    # Run it once.
    found = lookup_boto(s3_key)
    # Prime the caches with this finding.
    cache_key = hashlib.md5(force_bytes(
        f'benchmarking:caching_vs_boto:{s3_key}'
    )).hexdigest()
    caches['default'].set(cache_key, found, 60)
    caches['local'].set(cache_key, found, 60)

    # Now run it 'iterations' times and measure.
    times = {
        'boto': [],
        'local': [],
        'default': [],
    }
    for _ in range(iterations):
        with metrics.timer('benchmarking_cachingvsboto_boto'):
            t0 = time.time()
            lookup_boto(s3_key)
            t1 = time.time()
            times['boto'].append(t1 - t0)
        with metrics.timer('benchmarking_cachingvsboto_local'):
            t0 = time.time()
            caches['local'].get(cache_key)
            t1 = time.time()
            times['local'].append(t1 - t0)
        with metrics.timer('benchmarking_cachingvsboto_default'):
            t0 = time.time()
            caches['default'].get(cache_key)
            t1 = time.time()
            times['default'].append(t1 - t0)

    def summorize(numbers):
        return {
            'calls': len(numbers),
            'sum': sum(numbers),
            'mean': statistics.mean(numbers),
            'median': statistics.median(numbers),
        }
    context['found_in_s3'] = found
    context['results'] = {
        'boto': summorize(times['boto']),
        'local': summorize(times['local']),
        'default': summorize(times['default']),
    }

    return http.JsonResponse(context)
