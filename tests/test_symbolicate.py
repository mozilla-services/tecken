# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import requests
from markus.testing import MetricsMock
from markus import INCR, GAUGE

from django.core.urlresolvers import reverse
from django.core.cache import caches

from tecken.symbolicate.views import (
    SymbolicateJSON,
    LogCacheHitsMixin,
)


def test_log_cache_hits_and_misses(clear_redis):
    instance = LogCacheHitsMixin()

    with MetricsMock() as metrics_mock:
        # A hit!
        instance.log_symbol_cache_hit()
        # Another hit!
        instance.log_symbol_cache_hit()
        # A miss
        instance.log_symbol_cache_miss()

        records = metrics_mock.get_records()
        assert records[0] == (INCR, 'tecken.cache_hit', 1, None)
        assert records[1] == (INCR, 'tecken.cache_hit', 1, None)
        assert records[2] == (INCR, 'tecken.cache_miss', 1, None)


def test_log_cache_evictions_from_metrics_view(client, clear_redis, settings):
    settings.MARKUS_BACKENDS = [{
        'class': 'tecken.markus_extra.CacheMetrics',
    }]
    instance = LogCacheHitsMixin()
    for i in range(10):
        instance.log_symbol_cache_hit()
    for i in range(2):
        instance.log_symbol_cache_miss()
    caches['store'].set('symbol:foo', 'something')
    caches['store'].set('symbol:buz', 'else')
    caches['store'].set('symbol:bar', 'different')
    caches['store'].set('symbol:bar', 'changed')

    url = reverse('symbolicate:metrics')
    response = client.get(url)
    metrics = response.json()
    assert metrics['hits'] == 10
    assert metrics['misses'] == 2
    assert metrics['keys'] == 3


def test_symbolicate_json_bad_inputs(client, json_poster):
    url = reverse('symbolicate:symbolicate_json')
    response = client.get(url)
    assert response.status_code == 405
    assert response.json()['error']

    # No request.body JSON at all
    response = client.post(url)
    assert response.status_code == 400
    assert response.json()['error']

    # Some request.body JSON but broken
    response = json_poster(url, '{sqrt:-1}')
    assert response.status_code == 400
    assert response.json()['error']

    # Technically valid JSON but not a dict
    response = json_poster(url, True)
    assert response.status_code == 400
    assert response.json()['error']

    # A dict but empty
    response = json_poster(url, {})
    assert response.status_code == 400
    assert response.json()['error']

    # Valid JSON input but wrong version number
    response = json_poster(url, {
        'stacks': [],
        'memoryMap': [],
        'version': 999,
    })
    assert response.status_code == 400
    assert response.json()['error']


SAMPLE_SYMBOL_CONTENT = {
    'xul.sym': """
MODULE windows x86 44E4EC8C2F41492B9369D6B9A059577C2 xul.pdb
INFO CODE_ID 54AF957E1B34000 xul.dll

FILE 1 c:/program files (x86)/windows kits/8.0/include/shared/sal.h
FILE 2 c:/program files (x86)/windows kits/8.0/include/shared/concurrencysal.h
FILE 3 c:/program files (x86)/microsoft visual studio 10.0/vc/include/vadefs.h
FUNC 0 junkline
FUNC 26791a 592 4 XREMain::XRE_mainRun()
FUNC b2e3f7 2b4 4 XREMain::XRE_mainRun()
    """,
    'wntdll.sym': """
MODULE windows x86 D74F79EB1F8D4A45ABCD2F476CCABACC2 wntdll.pdb

PUBLIC 10070 10 KiUserCallbackExceptionHandler
PUBLIC 100dc c KiUserCallbackDispatcher
PUBLIC 10124 8 KiUserExceptionDispatcher
PUBLIC 10174 0 KiRaiseUserExceptionDispatcher
PUBLIC junk

    """
}


def test_symbolicate_json_happy_path_django_view(
    json_poster,
    clear_redis,
    settings,
    requestsmock,
    metricsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )

    url = reverse('symbolicate:symbolicate_json')
    response = json_poster(url, {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    })
    result = response.json()
    assert result['knownModules'] == [True, True]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]

    metrics_records = metricsmock.get_records()
    assert metrics_records[0] == (INCR, 'tecken.cache_miss', 1, None)
    assert metrics_records[1] == (INCR, 'tecken.cache_miss', 1, None)

    # The reason these numbers are hardcoded is because we know
    # predictable that the size of the pickled symbol map strings.
    metricsmock.has_record(GAUGE, 'tecken.storing_symbol', 76)
    metricsmock.has_record(GAUGE, 'tecken.storing_symbol', 165)

    # Since the amount of memory configured and used in the Redis
    # store, we can't use metricsmock.has_record()
    memory_gauges = [
        record for record in metrics_records
        if record[0] == GAUGE and 'store_memory' in record[1]
    ]
    assert len(memory_gauges) == 2

    # Because of a legacy we want this to be possible on the / endpoint
    response = json_poster(reverse('dashboard'), {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    })
    result_second = response.json()
    assert result_second == result


def test_symbolicate_json_one_cache_lookup_per_symbol(
    clear_redis,
    settings,
    requestsmock
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = SymbolicateJSON(
        # This will draw from the 2nd memory_map item TWICE
        stacks=[[[0, 11723767], [1, 65802], [1, 55802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2'],
        ],
        debug=True,
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, True]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)',
            'KiRaiseUserExceptionDispatcher (in wntdll.pdb)',
        ]
    ]
    assert result['debug']['downloads']['count'] == 2
    # This should be 2 because even though 'memory_map[0]' is needed
    # once and 'memory_map[1]' is needed twice, it should only be
    # done a total of 2 times because the symbol is repeating once.
    assert result['debug']['cache_lookups']['count'] == 2


def test_symbolicate_json_bad_module_indexes(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[-1, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ]
    )
    result = symbolicator.result
    assert result['knownModules'] == [False, True]
    assert result['symbolicatedStacks'] == [
        [
            hex(11723767),
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]


def test_symbolicate_json_bad_module_offset(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[-1, 1.00000000], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ]
    )
    result = symbolicator.result
    assert result['knownModules'] == [False, True]
    assert result['symbolicatedStacks'] == [
        [
            str(1.0000000),
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]


def test_symbolicate_json_happy_path_with_debug(
    clear_redis,
    settings,
    requestsmock
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = SymbolicateJSON(
        debug=True,
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, True]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]
    assert result['debug']['stacks']['count'] == 2
    assert result['debug']['stacks']['real'] == 2
    assert result['debug']['time'] > 0.0
    # Two cache lookups were attempted
    assert result['debug']['cache_lookups']['count'] == 2
    assert result['debug']['cache_lookups']['size'] == 0.0
    assert result['debug']['cache_lookups']['time'] > 0.0
    assert result['debug']['downloads']['count'] == 2
    assert result['debug']['downloads']['size'] > 0.0
    assert result['debug']['downloads']['time'] > 0.0
    assert result['debug']['modules']['count'] == 2
    assert result['debug']['modules']['stacks_per_module'] == {
        'xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2': 1,
        'wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2': 1,
    }

    # Look it up again, and this time the debug should indicate that
    # we drew from the cache.
    symbolicator = SymbolicateJSON(
        debug=True,
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, True]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]
    assert result['debug']['stacks']['real'] == 2
    assert result['debug']['stacks']['count'] == 2
    assert result['debug']['time'] > 0.0
    assert result['debug']['cache_lookups']['count'] == 2
    assert result['debug']['cache_lookups']['size'] > 0.0
    assert result['debug']['cache_lookups']['time'] > 0.0
    assert result['debug']['downloads']['count'] == 0
    assert result['debug']['downloads']['size'] == 0.0
    assert result['debug']['downloads']['time'] == 0.0


def test_symbolicate_json_one_symbol_not_found(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Not found',
        status_code=404
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            '0x1010a (in wntdll.pdb)'
        ]
    ]


def test_symbolicate_json_one_symbol_not_found_with_debug(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Not found',
        status_code=404
    )
    symbolicator = SymbolicateJSON(
        debug=True,
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    # It should work but because only 1 file could be downloaded,
    # there'll be no measurement of the one that 404 failed.
    assert result['debug']['downloads']['count'] == 1


def test_symbolicate_json_one_symbol_empty(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=''
    )
    symbolicator = SymbolicateJSON(
        debug=True,
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            '0x1010a (in wntdll.pdb)'
        ]
    ]
    assert result['debug']['downloads']['count'] == 2

    # Run it again, and despite that we failed to cache the second
    # symbol failed, that failure should be "cached".
    symbolicator = SymbolicateJSON(
        debug=True,
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['debug']['downloads']['count'] == 0


def test_symbolicate_json_one_symbol_500_error(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Interval Server Error',
        status_code=500
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_sslerror(
    clear_redis,
    settings,
    requestsmock,
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.SSLError
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_readtimeout(
    clear_redis,
    settings,
    requestsmock
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.ReadTimeout
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_connectionerror(
    clear_redis,
    settings,
    requestsmock
):
    settings.SYMBOL_URLS = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.ConnectionError
    )
    symbolicator = SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]
