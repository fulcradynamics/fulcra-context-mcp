"""Direct mesh writes use only synthetic per-request clients."""
import json
from copy import deepcopy

import pytest

from conftest import FAKE_USER_ID
from fulcra_mcp import tools

PEER = '00000000-0000-0000-0000-000000000002'
OTHER = '00000000-0000-0000-0000-000000000003'
OUTBOX = 'MomentAnnotation/00000000-0000-0000-0000-000000000004'
MID = '00000000-0000-0000-0000-000000000005'
GRANT = '00000000-0000-0000-0000-000000000006'
ARGS = dict(peer_userid=PEER, outbox=OUTBOX, peer_agent='Hermes', body='  Hello\npeer  ', mid=MID)
ENV = dict(v=1, mid=MID, to='Hermes', to_user=PEER, kind='directive', pri='P2', slug='mesh-message', body=ARGS['body'])


@pytest.fixture
def backend(fake_fulcra, monkeypatch):
    fake_fulcra.resolve_data_type.return_value = [dict(id=OUTBOX, fulcra_userid=FAKE_USER_ID,
        name='Mesh Outbox: ChatGPT', recordable=True, api_version='v1alpha1')]
    fake_fulcra.get_datashares.return_value = [dict(id=GRANT, share_all_data=False,
        fulcra_data_types=[OUTBOX], permissions=[dict(allowed_fulcra_userid=PEER)], group_permissions=[])]
    fake_fulcra.validate_records.return_value = []
    rows = []
    monkeypatch.setattr(tools.records, 'get_records', lambda api, entry, start, end: deepcopy(rows))
    def write(target, data, version):
        assert target == 'MomentAnnotation' and version == 'v1alpha1'
        assert data[0]['sources'] == ['com.fulcradynamics.mcp', 'com.fulcradynamics.annotation.' + OUTBOX.split('/')[1]]
        rows.extend(data)
        return {'upload_id': 'synthetic'}
    fake_fulcra.record_data_type.side_effect = write
    return fake_fulcra, rows


async def test_verified_post_and_duplicate_readback(call, backend):
    fake, rows = backend
    result = json.loads(await call('mesh_send', ARGS))
    assert result['status'] == 'posted' and result['peer_acknowledged'] is False
    assert result['mid'] == MID and result['outbox'] == OUTBOX
    assert json.loads(rows[0]['note']) == ENV
    again = json.loads(await call('mesh_send', ARGS))
    assert again['status'] == 'posted'
    assert fake.record_data_type.call_count == 1
    fake.create_datashare.assert_not_called()
    fake.create_annotation.assert_not_called()


@pytest.mark.parametrize('change', [
    {'share_all_data': True}, {'fulcra_data_types': ['MomentAnnotation']},
    {'fulcra_data_types': ['*']}, {'fulcra_data_types': ['MomentAnnotation/*']}, {'fulcra_data_types': [OUTBOX, 'StepCount']},
    {'permissions': [{'allowed_fulcra_userid': OTHER}]},
    {'permissions': [{'allowed_fulcra_userid': PEER}, {'allowed_fulcra_userid': OTHER}]},
    {'group_permissions': [{'allowed_group_id': OTHER}]}, {'group_id': OTHER},
    {'time_start': '2026-01-01T00:00:00Z'}, {'time_end': '2027-01-01T00:00:00Z'},
    {'file_paths': ['/private/']}, {'files': ['private']}, {'share_all_data': None},
])
async def test_all_covering_grants_checked(call, backend, change):
    fake, _ = backend
    extra = {**deepcopy(fake.get_datashares.return_value[0]), **change}
    fake.get_datashares.return_value.append(extra)
    result = json.loads(await call('mesh_send', ARGS))
    assert result['status'] == 'rejected'
    fake.record_data_type.assert_not_called()


@pytest.mark.parametrize('case', ['no_grant', 'duplicate_grant', 'foreign', 'ambiguous', 'inactive', 'deleted', 'nonrecordable', 'self', 'malformed', 'blank', 'conflict'])
async def test_refuses_unsafe_or_ambiguous_target(call, backend, case):
    fake, rows = backend
    args = dict(ARGS)
    if case == 'no_grant': fake.get_datashares.return_value = []
    if case == 'duplicate_grant': fake.get_datashares.return_value *= 2
    if case == 'foreign': fake.resolve_data_type.return_value[0]['fulcra_userid'] = OTHER
    if case == 'ambiguous': fake.resolve_data_type.return_value *= 2
    if case == 'inactive': fake.resolve_data_type.return_value[0]['deprecated'] = True
    if case == 'deleted': fake.resolve_data_type.return_value[0]['deleted_at'] = '2026-01-01T00:00:00Z'
    if case == 'nonrecordable': fake.resolve_data_type.return_value[0]['recordable'] = False
    if case == 'self': args['peer_userid'] = FAKE_USER_ID
    if case == 'malformed': args['outbox'] += ' '
    if case == 'blank': args['body'] = ' \n'
    if case == 'conflict': rows.append({'note': json.dumps({**ENV, 'body': 'different'})})
    assert json.loads(await call('mesh_send', args))['status'] == 'rejected'
    fake.record_data_type.assert_not_called()


@pytest.mark.parametrize('failure', ['write', 'missing', 'readback'])
async def test_uncertainty_never_claims_posted_or_delivered(call, backend, monkeypatch, failure):
    fake, _ = backend
    fake.record_data_type.side_effect = RuntimeError('synthetic') if failure == 'write' else lambda *args: {}
    if failure == 'readback':
        reads = iter([[], RuntimeError('synthetic')])
        def read(*args):
            value = next(reads)
            if isinstance(value, Exception): raise value
            return value
        monkeypatch.setattr(tools.records, 'get_records', read)
    result = json.loads(await call('mesh_send', ARGS))
    assert result['status'] == 'uncertain'
    assert result['peer_acknowledged'] is False
    assert result['mid'] == MID
    assert fake.record_data_type.call_count == 1


async def test_registration_visible_to_model_and_app(client):
    tool = next(t for t in await client.list_tools() if t.name == 'mesh_send')
    assert tool.meta['ui']['visibility'] == ['model', 'app']
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.idempotentHint is False


@pytest.mark.parametrize('change', ['account', 'revoked', 'broadened'])
async def test_rechecks_immediately_before_write(call, backend, change):
    fake, _ = backend
    if change == 'account': fake.get_fulcra_userid.side_effect = [FAKE_USER_ID, OTHER]
    else:
        original = deepcopy(fake.get_datashares.return_value)
        altered = [] if change == 'revoked' else [{**original[0], 'share_all_data': True}]
        fake.get_datashares.side_effect = [original, altered]
    assert json.loads(await call('mesh_send', ARGS))['status'] == 'rejected'
    fake.record_data_type.assert_not_called()


async def test_unrelated_grant_does_not_block_send(call, backend):
    fake, _ = backend
    fake.get_datashares.return_value.append(dict(share_all_data=False, fulcra_data_types=['StepCount'], permissions=[dict(allowed_fulcra_userid=OTHER)]))
    assert json.loads(await call('mesh_send', ARGS))['status'] == 'posted'
