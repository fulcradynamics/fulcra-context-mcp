"""Exercise skill-style whole-second queries through the public tool and SDK.

Transport is synthetic: historical backend acceptance/completeness is not proven.
"""
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import promql_parser
import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from fulcra_mcp import tools

TYPE = 'Event/00000000-0000-4000-8000-000000000010'
PEER = '00000000-0000-4000-8000-000000000002'
UTC = timezone.utc


async def test_century_windows_real_sdk_and_lossless_rows(call, monkeypatch):
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': '00000000-0000-4000-8000-000000000001'})
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    windows = []
    row = dict(id='first', kind='ack', start_time='0001-01-01T00:00:00.123456Z',
               end_time='0001-01-01T00:00:00.123456Z', extra={'keep': [None, 4]})
    def transport(req):
        url = urlparse(req.full_url); query = parse_qs(url.query)
        assert query['fulcra_userid'] == [PEER]
        if url.path == '/data/v1/catalog':
            return BytesIO(json.dumps([dict(id=TYPE, api_version='v1', fulcra_userid=PEER, record_spec={'type': 'event'})]).encode())
        assert url.path == '/data/v1/records'
        parsed = promql_parser.parse(query['q'][0])
        # The parser accepts negative anchors, but its Python datetime accessor
        # panics before epoch. Inspect the actual serialized integer instead.
        end = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=int(query['q'][0].rsplit('@', 1)[1]))
        start = end - parsed.range
        windows.append((start, end))
        return BytesIO((json.dumps(row) + '\n').encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    start = datetime(1, 1, 1, tzinfo=UTC)
    now = datetime(2026, 10, 20, 12, 0, 0, 123456, tzinfo=UTC)
    final = now.replace(microsecond=0) + timedelta(seconds=1)
    seen = {}
    while start < final:
        end = min(start.replace(year=start.year + 100), final)
        text = await call('get_records', dict(data_type=TYPE, fulcra_userid=PEER,
                          start_time=start.isoformat(), end_time=end.isoformat()))
        assert 'showing the first' not in text
        rows = json.loads(text.split(': ', 1)[1])
        assert rows == [row]  # no compacting kinds, IDs, fractions or custom fields
        for value in rows:
            assert value['id'] not in seen or seen[value['id']] == value
            seen[value['id']] = value
        start = end
    assert windows[0][0] == datetime(1, 1, 1, tzinfo=UTC)
    assert windows[-1][1] == final
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:]))
    assert all(not s.microsecond and not e.microsecond and 0 < (e-s).total_seconds() < 2**32
               and e <= s.replace(year=s.year + 100) for s, e in windows)
    assert list(seen.values()) == [row]  # an earliest ack cannot become a handshake


@pytest.mark.parametrize('conflict,tie', [(False, False), (True, False), (False, True)])
async def test_split_cap_boundary_identity_and_earliest_ties(call, fake_fulcra, monkeypatch, conflict, tie):
    # Test the generic projection at each step, including its truncation signal.
    monkeypatch.setattr(tools, 'MAX_RECORDS', 2)
    fake_fulcra.resolve_data_type.return_value = [dict(id=TYPE, api_version='v1', fulcra_userid=PEER, record_spec={'type': 'event'})]
    first = dict(id='a', kind='message', topic='handshake ' + 'a'*32,
                 start_time='2000-01-01T00:00:01Z')
    later = dict(id='b', kind='message', start_time='2000-01-01T00:00:01Z' if tie else '2000-01-01T00:00:02Z')
    boundary = {**first, **({'topic': 'conflicting'} if conflict else {})}
    fake_fulcra.fulcra_v1_records.side_effect = ['\n'.join(json.dumps(r) for r in rows)
        for rows in ([first, later, boundary], [first], [boundary, later])]
    async def read(start, end):
        text = await call('get_records', dict(data_type=TYPE, fulcra_userid=PEER,
            start_time=f'2000-01-01T00:00:0{start}Z', end_time=f'2000-01-01T00:00:0{end}Z'))
        return text, json.loads(text.split(': ', 1)[1])
    text, _ = await read(0, 4)
    assert 'showing the first 2 of 3' in text
    _, left = await read(0, 2); _, right = await read(2, 4)
    seen = {}; conflicts = False
    for row in left + right:
        conflicts |= row['id'] in seen and seen[row['id']] != row
        seen.setdefault(row['id'], row)
    assert conflicts == conflict
    earliest = min(r['start_time'] for r in seen.values())
    candidates = [r for r in seen.values() if r['start_time'] == earliest]
    assert (not conflicts and len(candidates) == 1) == (not conflict and not tie)


async def test_one_second_cap_remains_explicitly_incomplete(call, fake_fulcra, monkeypatch):
    monkeypatch.setattr(tools, 'MAX_RECORDS', 2)
    fake_fulcra.resolve_data_type.return_value = [dict(id=TYPE, api_version='v1', fulcra_userid=PEER, record_spec={'type': 'event'})]
    fake_fulcra.fulcra_v1_records.return_value = '\n'.join(json.dumps(dict(id=str(i), start_time='2000-01-01T00:00:00.5Z')) for i in range(3))
    text = await call('get_records', dict(data_type=TYPE, fulcra_userid=PEER,
        start_time='2000-01-01T00:00:00Z', end_time='2000-01-01T00:00:01Z'))
    assert 'showing the first 2 of 3' in text  # cannot split further at whole seconds
