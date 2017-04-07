import requests
import requests_mock

from django.core.urlresolvers import reverse
from django.core.cache import cache, caches

from tecken.symbolicate.views import (
    SymbolicateJSON,
    LogCacheHitsMixin,
)


def test_log_cache_hits_and_misses(clear_redis):
    instance = LogCacheHitsMixin()

    # A hit!
    instance.log_symbol_cache_hit('foo')
    assert cache.get('foo') == 1

    # Another hit!
    instance.log_symbol_cache_hit('foo')
    assert cache.get('foo') == 2

    # A miss
    instance.log_symbol_cache_miss('bar')
    assert cache.get('bar') == 0

    # But suppose, what once used to work is now a miss
    instance.log_symbol_cache_miss('foo')
    assert cache.get('foo') == 0
    assert cache.get('foo:evicted') == 1


def test_log_cache_evictions_from_metrics_view(client, clear_redis):
    instance = LogCacheHitsMixin()
    instance.log_symbol_cache_hit('symbol:foo')
    instance.log_symbol_cache_hit('symbol:foo')
    instance.log_symbol_cache_hit('symbol:buz')
    instance.log_symbol_cache_miss('symbol:bar')
    instance.log_symbol_cache_miss('symbol:foo')
    caches['store'].set('symbol:foo', 'something')
    caches['store'].set('symbol:buz', 'else')
    caches['store'].set('symbol:bar', 'different')

    url = reverse('symbolicate:metrics')
    response = client.get(url)
    metrics = response.json()
    assert metrics['evictions'] == 1
    assert metrics['hits'] == 1
    assert metrics['keys'] == 3
    assert metrics['misses'] == 2


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


def test_symbolicate_json_happy_path_django_view(json_poster, clear_redis):
    url = reverse('symbolicate:symbolicate_json')
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
            text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
        )
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

        # Because of a legacy we want this to be possible on the / endpoint
        response = json_poster('/', {
            'stacks': [[[0, 11723767], [1, 65802]]],
            'memoryMap': [
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
            'version': 4,
        })
        result_second = response.json()
        assert result_second == result


def test_symbolicate_json_bad_module_indexes(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_bad_module_offset(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_cache_hits_logged(client, clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
            text=SAMPLE_SYMBOL_CONTENT['wntdll.sym']
        )
        symbolicator = SymbolicateJSON(
            stacks=[[[0, 11723767], [1, 65802]]],
            memory_map=[
                ['xul.pdb', '44E4EC8C2F41492B9369D6B9A059577C2'],
                ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
            ],
        )
        assert symbolicator.result['symbolicatedStacks']

        url = reverse('symbolicate:metrics')
        response = client.get(url)
        metrics = response.json()
        assert metrics['ratio_of_hits'] == 0.0
        assert metrics['percent_of_hits'] == 0.0
        assert metrics['hits'] == 0
        assert metrics['evictions'] == 0
        assert metrics['misses'] == 2
        assert metrics['maxmemory']['bytes'] > 0
        assert metrics['maxmemory']['human']
        assert metrics['used_memory']['bytes'] > 0
        assert metrics['used_memory']['human']


def test_symbolicate_json_happy_path_with_debug(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_not_found(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_not_found_with_debug(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_content_enc_err(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
            exc=requests.exceptions.ContentDecodingError
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


def test_symbolicate_json_one_symbol_empty(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_500_error(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_sslerror(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_readtimeout(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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


def test_symbolicate_json_one_symbol_connectionerror(clear_redis):
    with requests_mock.mock() as m:
        m.get(
            'https://s3.example.com/public/xul.pdb/44E4EC8C2F41492B9369D6B9'
            'A059577C2/xul.sym',
            text=SAMPLE_SYMBOL_CONTENT['xul.sym']
        )
        m.get(
            'https://s3.example.com/public/wntdll.pdb/D74F79EB1F8D4A45ABCD2'
            'F476CCABACC2/wntdll.sym',
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
