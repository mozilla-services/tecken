# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import BytesIO

import requests
from markus import INCR, GAUGE
from botocore.exceptions import ClientError

from django.urls import reverse
from django.core.cache import caches

from tecken.base.symboldownloader import SymbolDownloader
from tecken.symbolicate import views
from tecken.symbolicate.tasks import invalidate_symbolicate_cache


def reload_downloader(urls):
    """Because the tecken.download.views module has a global instance
    of SymbolDownloader created at start-up, it's impossible to easily
    change the URL if you want to test clients with a different URL.
    This function hotfixes that instance to use a different URL(s).
    """
    if isinstance(urls, str):
        urls = tuple([urls])
    views.downloader = SymbolDownloader(urls)


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


def test_client_happy_path(
    json_poster,
    clear_redis_store,
    requestsmock,
    metricsmock,
):
    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
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
    assert metrics_records[0] == (
        INCR, 'tecken.symbolicate_cache_miss', 1, None
    )
    assert metrics_records[1] == (
        INCR, 'tecken.symbolicate_cache_miss', 1, None
    )

    # The reason these numbers are hardcoded is because we know
    # predictable that the size of the pickled symbol map strings.
    metricsmock.has_record(GAUGE, 'tecken.storing_symbol', 76)
    metricsmock.has_record(GAUGE, 'tecken.storing_symbol', 165)

    # Since the amount of memory configured and used in the Redis
    # store, we can't use metricsmock.has_record()
    memory_gauges = [
        record for record in metrics_records
        if record[0] == GAUGE and 'used_memory' in record[1]
    ]
    assert len(memory_gauges) == 2

    # Called the first time it had to do a symbol store
    metricsmock.has_record(GAUGE, 'tecken.store_keys', 1, None)
    # Called twice because this test depends on downloading two symbols
    metricsmock.has_record(GAUGE, 'tecken.store_keys', 2, None)

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


def test_symbolicate_json_one_cache_lookup(clear_redis_store, requestsmock):
    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = views.SymbolicateJSON(
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
    # 'xul.pdb' is needed once, 'wntdll.pdb' is needed twice
    # but it should only require 1 cache lookup.
    assert result['debug']['cache_lookups']['count'] == 2


def test_symbolicate_json_lru_causing_mischief(
    clear_redis_store,
    requestsmock
):
    """Warning! This test is quite fragile.
    It runs the symbolication twice. After the first run, the test
    manually goes in and deletes the hash map.
    This requires "direct access" to the Redis store but it's to
    simulate what the LRU naturally does but without waiting for
    time or max. memory usage.
    """

    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = views.SymbolicateJSON(
        # This will draw from the 2nd memory_map item TWICE
        stacks=[[[0, 11723767], [1, 65802]]],
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
            # 'KiRaiseUserExceptionDispatcher (in wntdll.pdb)',
        ]
    ]
    assert result['debug']['downloads']['count'] == 2
    assert result['debug']['cache_lookups']['count'] == 2

    # Pretend the LRU evicted the 'xul.pdb/...' hashmap.
    store = caches['store']
    hashmap_key, = [
        key for key in store.iter_keys('*')
        if not key.endswith(':keys') and 'xul.pdb' in key
    ]
    assert store.delete(hashmap_key)

    # Same symbolication one more time
    symbolicator = views.SymbolicateJSON(
        # This will draw from the 2nd memory_map item TWICE
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2'],
        ],
        debug=True,
    )
    result_second = symbolicator.result
    # Because the xul.pdb symbol had to be downloaded again
    assert result_second['debug']['downloads']['count'] == 1


def test_symbolicate_json_bad_module_indexes(clear_redis_store, requestsmock):
    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = views.SymbolicateJSON(
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


def test_symbolicate_json_bad_module_offset(clear_redis_store, requestsmock):
    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = views.SymbolicateJSON(
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
    clear_redis_store,
    requestsmock
):
    # XXX Stop using the public downloader.
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
    )
    symbolicator = views.SymbolicateJSON(
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
    # One cache lookup was attempted
    assert result['debug']['cache_lookups']['count'] == 2
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
    symbolicator = views.SymbolicateJSON(
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
    assert result['debug']['cache_lookups']['count'] == 5
    assert result['debug']['cache_lookups']['time'] > 0.0
    assert result['debug']['downloads']['count'] == 0
    assert result['debug']['downloads']['size'] == 0.0
    assert result['debug']['downloads']['time'] == 0.0


def test_symbolicate_json_one_symbol_not_found(
    clear_redis_store,
    requestsmock
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Not found',
        status_code=404
    )
    symbolicator = views.SymbolicateJSON(
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
    clear_redis_store,
    requestsmock,
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Not found',
        status_code=404
    )
    symbolicator = views.SymbolicateJSON(
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
    clear_redis_store,
    requestsmock,
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text=''
    )
    symbolicator = views.SymbolicateJSON(
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
    symbolicator = views.SymbolicateJSON(
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
    clear_redis_store,
    requestsmock,
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )

    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        text='Interval Server Error',
        status_code=500
    )
    symbolicator = views.SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_sslerror(
    clear_redis_store,
    requestsmock,
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.SSLError
    )
    symbolicator = views.SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_readtimeout(
    clear_redis_store,
    requestsmock
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.ReadTimeout
    )
    symbolicator = views.SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_symbolicate_json_one_symbol_connectionerror(
    clear_redis_store,
    requestsmock
):
    reload_downloader(
        'https://s3.example.com/public/prefix/?access=public',
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=SAMPLE_SYMBOL_CONTENT['xul.sym']
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/v0/wntdll.pdb/'
        'D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym',
        exc=requests.exceptions.ConnectionError
    )
    symbolicator = views.SymbolicateJSON(
        stacks=[[[0, 11723767], [1, 65802]]],
        memory_map=[
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    )
    result = symbolicator.result
    assert result['knownModules'] == [True, False]


def test_invalidate_symbols_invalidates_cache(
    clear_redis_store,
    botomock,
    json_poster,
    settings
):
    settings.SYMBOL_URLS = ['https://s3.example.com/private/prefix/']
    reload_downloader('https://s3.example.com/private/prefix/')

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'GetObject'
        if mock_api_calls:
            # This means you're here for the second time.
            # Pretend we have the symbol this time.
            mock_api_calls.append((operation_name, api_params))
            return {
                'Body': BytesIO(
                    bytes(SAMPLE_SYMBOL_CONTENT['xul.sym'], 'utf-8')
                )
            }
        else:
            mock_api_calls.append((operation_name, api_params))
            if api_params['Key'].endswith('xul.sym'):
                parsed_response = {
                    'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'},
                }
                raise ClientError(parsed_response, operation_name)
            raise NotImplementedError(api_params)

    with botomock(mock_api_call):
        url = reverse('symbolicate:symbolicate_json')
        response = json_poster(url, {
            'stacks': [[[0, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
            'version': 4,
        })
        result = response.json()
        assert result['knownModules'] == [False]
        assert len(mock_api_calls) == 1

        response = json_poster(url, {
            'stacks': [[[0, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
            'version': 4,
        })
        result = response.json()
        assert result['knownModules'] == [False]
        # Expected because the cache stores that the file can't be found.
        assert len(mock_api_calls) == 1

        # Pretend an upload comes in and stores those symbols.
        invalidate_symbolicate_cache([
            ('xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'),
        ])
        response = json_poster(url, {
            'stacks': [[[0, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
            'version': 4,
        })
        result = response.json()
        assert result['knownModules'] == [True]
        assert result['symbolicatedStacks'] == [
            ['XREMain::XRE_mainRun() (in xul.pdb)']
        ]
        assert len(mock_api_calls) == 2
