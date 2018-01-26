# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import BytesIO

import botocore
import requests
import pytest
from markus import INCR, GAUGE
from botocore.exceptions import ClientError

from django.urls import reverse
from django.core.cache import caches

from tecken.base.symboldownloader import SymbolDownloader, SymbolDownloadError
from tecken.symbolicate import views
from tecken.symbolicate.tasks import invalidate_symbolicate_cache


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

    """,
    'firefox.sym': """
MODULE windows x86 9A8C8930C5E935E3B441CC9D6E72BB990 firefox.pdb

FUNC eb0 699 0 main
FUNC 1550 cf 0 Output
1550 6f 60 1
15bf 2e 62 1
15ed 12 65 1
15ff 12 65 1
1611 e 97 1
FUNC 1620 d6 0 int SprintfLiteral<1024ul>(char (&) [1024ul], char const*, ...)
1620 6f 32 3
168f 36 34 3
16c5 10 24 3
16d5 11 25 3
16e6 10 37 3
FUNC 1700 149 0 mozilla::BinaryPath::GetFile(char const*, nsIFile**)
PUBLIC 0 0 _mh_execute_header
PUBLIC e70 0 start
PUBLIC 3160 0 _ZL9kXULFuncs
PUBLIC 3230 0 _ZL8sAppData
PUBLIC 32b0 0 NXArgc
PUBLIC 32b8 0 NXArgv
PUBLIC 32c0 0 environ
PUBLIC 32c8 0 __progname
PUBLIC 32d0 0 XRE_GetFileFromPath
PUBLIC 32d8 0 XRE_CreateAppData
PUBLIC 32e0 0 XRE_FreeAppData
PUBLIC 32e8 0 XRE_TelemetryAccumulate
PUBLIC 32f0 0 XRE_StartupTimelineRecord
PUBLIC 32f8 0 XRE_main
PUBLIC 3300 0 XRE_StopLateWriteChecks
PUBLIC 3308 0 XRE_XPCShellMain
PUBLIC 3310 0 XRE_GetProcessType
PUBLIC 3318 0 XRE_SetProcessType
PUBLIC 3320 0 XRE_InitChildProcess
PUBLIC 3328 0 XRE_EnableSameExecutableForContentProc
PUBLIC 3330 0 _ZL4sTop
PUBLIC 3338 0 _ZL10do_preload
PUBLIC 3340 0 _ZL14xpcomFunctions

    """
}


def reload_downloader(urls):
    """Because the tecken.download.views module has a global instance
    of SymbolDownloader created at start-up, it's impossible to easily
    change the URL if you want to test clients with a different URL.
    This function hotfixes that instance to use a different URL(s).
    """
    if isinstance(urls, str):
        urls = tuple([urls])
    views.downloader = SymbolDownloader(urls)


def default_mock_api_call(self, operation_name, api_params):
    """Use when nothing weird with the boto gets is expected"""
    if operation_name == 'GetObject':
        filename = api_params['Key'].split('/')[-1]
        if filename in SAMPLE_SYMBOL_CONTENT:
            return {
                'Body': BytesIO(
                    SAMPLE_SYMBOL_CONTENT[filename].encode('utf-8')
                )
            }
        raise NotImplementedError(api_params)

    raise NotImplementedError(operation_name)


def test_symbolicate_v5_json_bad_inputs(client, json_poster):
    url = reverse('symbolicate:symbolicate_v5_json')
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

    # A dict but 'jobs' key empty
    response = json_poster(url, {'jobs': []})
    assert response.status_code == 400
    assert response.json()['error']

    # Not empty but the job lacks the required keys
    response = json_poster(url, {'jobs': [{'stacks': []}]})
    assert response.status_code == 400
    assert response.json()['error']

    # Both keys in the job but not lists
    response = json_poster(url, {'jobs': [{
        'stacks': 'string',
        'memoryMap': [],
    }]})
    assert response.status_code == 400
    assert response.json()['error']
    response = json_poster(url, {'jobs': [{
        'stacks': [],
        'memoryMap': 'string',
    }]})
    assert response.status_code == 400
    assert response.json()['error']


def test_symbolicate_v4_json_bad_inputs(client, json_poster):
    url = reverse('symbolicate:symbolicate_v4_json')
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


def test_client_happy_path_v5(
    json_poster,
    clear_redis_store,
    botomock,
    metricsmock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v5_json')
    with botomock(default_mock_api_call):
        job = {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
        }
        response = json_poster(url, {'jobs': [job]})
    result = response.json()
    assert len(result['results']) == 1
    result1 = result['results'][0]
    assert result1['stacks'] == [
        [
            {
                "module_offset": "0xb2e3f7",
                "module": "xul.pdb",
                "frame": 0,
                "function": "XREMain::XRE_mainRun()",
                "function_offset": "0x0"
            },
            {
                "module_offset": "0x1010a",
                "module": "wntdll.pdb",
                "frame": 1,
                "function": "KiUserCallbackDispatcher",
                "function_offset": "0x2e"
            }
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


def test_client_happy_path_v5_with_debug(
    json_poster,
    clear_redis_store,
    botomock,
    metricsmock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v5_json')
    with botomock(default_mock_api_call):
        job = {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
        }
        response = json_poster(url, {'jobs': [job]}, debug=True)
    result = response.json()
    assert len(result['results']) == 1
    result1 = result['results'][0]
    # There are other tests that do a better job of testing the debug
    # content.
    assert result1['debug']


def test_client_happy_path_v4(
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

    url = reverse('symbolicate:symbolicate_v4_json')
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


def test_symbolicate_through_root_gone(json_poster):
    # You *used* to be able to do a v4 symbolication using /.
    # That's deprecated now.
    # Because of a legacy we want this to be possible on the / endpoint
    response = json_poster(reverse('dashboard'), {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    })
    assert response.status_code == 410  # Gone


def test_symbolicate_v4_json_one_cache_lookup(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v4_json')
    with botomock(default_mock_api_call):
        response = json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802], [1, 55802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        }, debug=True)
    result = response.json()
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


def test_symbolicate_v4_json_lru_causing_mischief(
    json_poster,
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
    url = reverse('symbolicate:symbolicate_v4_json')
    response = json_poster(url, {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    }, debug=True)
    result = response.json()
    assert result['knownModules'] == [True, True]
    assert result['symbolicatedStacks'] == [
        [
            'XREMain::XRE_mainRun() (in xul.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)',
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
    response = json_poster(url, {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    }, debug=True)
    result_second = response.json()
    # symbolicator = views.SymbolicateJSON(debug=True)
    # result_second = symbolicator.symbolicate(
    #     # This will draw from the 2nd memory_map item TWICE
    #     stacks=[[[0, 11723767], [1, 65802]]],
    #     memory_map=[
    #         ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
    #         ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2'],
    #     ],
    # )
    # Because the xul.pdb symbol had to be downloaded again
    assert result_second['debug']['downloads']['count'] == 1


def test_symbolicate_v4_json_bad_module_indexes(
    json_poster,
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
    url = reverse('symbolicate:symbolicate_v4_json')
    response = json_poster(url, {
        'stacks': [[[-1, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    })
    result = response.json()
    assert result['knownModules'] == [False, True]
    assert result['symbolicatedStacks'] == [
        [
            f'{hex(11723767)} (in wntdll.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]


def test_symbolicate_v4_json_bad_module_offset(
    json_poster,
    clear_redis_store,
    botomock
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v4_json')
    with botomock(default_mock_api_call):
        response = json_poster(url, {
            'stacks': [[[-1, 1.00000000], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        })
    result = response.json()
    assert result['knownModules'] == [False, True]
    assert result['symbolicatedStacks'] == [
        [
            f'{str(1.0000000)} (in wntdll.pdb)',
            'KiUserCallbackDispatcher (in wntdll.pdb)'
        ]
    ]


def test_symbolicate_v4_json_happy_path_with_debug(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v4_json')
    with botomock(default_mock_api_call):
        response = json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        }, debug=True)
    result = response.json()
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
    with botomock(default_mock_api_call):
        response = json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        }, debug=True)
    result = response.json()
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


def test_symbolicate_v4_json_one_symbol_not_found_with_debug(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    def mock_api_call(self, operation_name, api_params):
        if operation_name == 'GetObject':
            filename = api_params['Key'].split('/')[-1]
            if filename == 'wntdll.sym':
                parsed_response = {
                    'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'},
                }
                raise ClientError(parsed_response, operation_name)
            if filename in SAMPLE_SYMBOL_CONTENT:
                return {
                    'Body': BytesIO(
                        SAMPLE_SYMBOL_CONTENT[filename].encode('utf-8')
                    )
                }
            raise NotImplementedError(api_params)

        raise NotImplementedError(operation_name)

    url = reverse('symbolicate:symbolicate_v4_json')
    with botomock(mock_api_call):
        response = json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        }, debug=True)
    result = response.json()
    # It should work but because only 1 file could be downloaded,
    # there'll be no measurement of the one that 404 failed.
    assert result['debug']['downloads']['count'] == 1


def test_symbolicate_v4_json_one_symbol_empty(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    def mock_api_call(self, operation_name, api_params):
        if operation_name == 'GetObject':
            filename = api_params['Key'].split('/')[-1]
            if filename == 'wntdll.sym':
                return {
                    'Body': BytesIO(b'')
                }
            if filename in SAMPLE_SYMBOL_CONTENT:
                return {
                    'Body': BytesIO(
                        SAMPLE_SYMBOL_CONTENT[filename].encode('utf-8')
                    )
                }
            raise NotImplementedError(api_params)

        raise NotImplementedError(operation_name)

    url = reverse('symbolicate:symbolicate_v4_json')
    with botomock(mock_api_call):
        response = json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        }, debug=True)
    result = response.json()
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
    response = json_poster(url, {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'version': 4,
    }, debug=True)
    result = response.json()
    assert result['debug']['downloads']['count'] == 0


def test_symbolicate_public_bucket_one_symbol_500_error(
    json_poster,
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
    url = reverse('symbolicate:symbolicate_v4_json')
    with pytest.raises(SymbolDownloadError):
        json_poster(url, {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        })


def test_symbolicate_public_bucket_one_symbol_sslerror(
    json_poster,
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
    url = reverse('symbolicate:symbolicate_v5_json')
    job = {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    }
    response = json_poster(url, {'jobs': [job]})
    assert response.status_code == 503

    url = reverse('symbolicate:symbolicate_v4_json')
    job['version'] = 4
    response = json_poster(url, job)
    assert response.status_code == 503


def test_symbolicate_public_bucket_one_symbol_readtimeout(
    json_poster,
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
    url = reverse('symbolicate:symbolicate_v5_json')
    job = {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    }
    response = json_poster(url, {'jobs': [job]})
    assert response.status_code == 503

    url = reverse('symbolicate:symbolicate_v4_json')
    job['version'] = 4
    response = json_poster(url, job)
    assert response.status_code == 503


def test_symbolicate_private_bucket_one_symbol_connectionerror(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    def mock_api_call(self, operation_name, api_params):
        if operation_name == 'GetObject':
            filename = api_params['Key'].split('/')[-1]
            if filename == 'wntdll.sym':
                raise botocore.exceptions.ConnectionError('so much hard!')
            if filename in SAMPLE_SYMBOL_CONTENT:
                return {
                    'Body': BytesIO(
                        SAMPLE_SYMBOL_CONTENT[filename].encode('utf-8')
                    )
                }
            raise NotImplementedError(api_params)

        raise NotImplementedError(operation_name)

    with botomock(mock_api_call):
        url = reverse('symbolicate:symbolicate_v5_json')
        job = {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
        }
        response = json_poster(url, {'jobs': [job]})
        assert response.status_code == 503

        url = reverse('symbolicate:symbolicate_v4_json')
        job['version'] = 4
        response = json_poster(url, job)
        assert response.status_code == 503


def test_symbolicate_v5_json_reused_memory_maps(
    json_poster,
    clear_redis_store,
    botomock,
):
    reload_downloader('https://s3.example.com/public/prefix/')

    url = reverse('symbolicate:symbolicate_v5_json')
    job1 = {
        'stacks': [[[0, 11723767], [1, 65802]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
    }
    job2 = {
        'stacks': [[[0, 10613656]]],
        'memoryMap': [
            ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
        ],
    }
    job3 = {
        'stacks': [[[0, 100]]],
        'memoryMap': [
            ['firefox.pdb', '9A8C8930C5E935E3B441CC9D6E72BB990'],
        ],
        'version': 4,
    }
    with botomock(default_mock_api_call):
        response = json_poster(url, {'jobs': [job1, job2, job3]}, debug=True)
    result = response.json()

    result1 = result['results'][0]
    assert result1['debug']['downloads']['count'] == 2
    assert result1['debug']['cache_lookups']['count'] == 2

    result2 = result['results'][1]
    assert result2['debug']['downloads']['count'] == 0
    assert result2['debug']['cache_lookups']['count'] == 0

    result3 = result['results'][2]
    assert result3['debug']['downloads']['count'] == 1
    assert result3['debug']['cache_lookups']['count'] == 2


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
        url = reverse('symbolicate:symbolicate_v5_json')
        response = json_poster(url, {
            'stacks': [[[0, 11723767]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
        })
        result = response.json()
        result1 = result['results'][0]
        stack1 = result1['stacks'][0]
        frame1 = stack1[0]
        assert 'function' not in frame1  # module couldn't be found
        assert len(mock_api_calls) == 1

        response = json_poster(url, {
            'stacks': [[[0, 11723767]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
            'version': 4,
        })
        result = response.json()
        result1 = result['results'][0]
        stack1 = result1['stacks'][0]
        frame1 = stack1[0]
        assert 'function' not in frame1  # module still couldn't be found
        # Expected because the cache stores that the file can't be found.
        assert len(mock_api_calls) == 1

        # Pretend an upload comes in and stores those symbols.
        invalidate_symbolicate_cache([
            ('xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'),
        ])
        response = json_poster(url, {
            'stacks': [[[0, 11723767]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2']
            ],
            'version': 4,
        })
        result = response.json()
        result1 = result['results'][0]
        stack1 = result1['stacks'][0]
        frame1 = stack1[0]
        assert frame1['function']
        assert frame1['function'] == 'XREMain::XRE_mainRun()'
        assert len(mock_api_calls) == 2
