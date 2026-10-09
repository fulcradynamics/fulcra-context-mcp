import importlib
import json
from unittest.mock import MagicMock
import pytest

import fulcra_mcp.tools as tools

TYPE_ID = 'MomentAnnotation/12345678-1234-4234-8234-123456789abc'


@pytest.fixture
def api(monkeypatch):
    api = MagicMock()
    api.get_fulcra_userid.return_value = 'own'
    api.entry = {'id': TYPE_ID, 'fulcra_userid': 'own', 'name': 'Mesh Outbox — peer',
                 'api_version': 'v1alpha1', 'description': 'Keep prose\n  exactly.',
                 'record_spec': {'schema': 'unchanged'}, 'deprecated': False,
                 'annotation_type': 'moment', 'spec': None, 'measurement_spec': None, 'tags': []}
    api.resolve_data_type.side_effect = lambda *a, **kw: [dict(api.entry)]
    def transport(path, *, method, authenticated, data=None):
        assert path == '/user/v1alpha1/annotation/' + TYPE_ID.split('/')[1]
        assert authenticated is True
        if method == 'PUT':
            api.entry.update(data)
        return json.dumps({**api.entry, 'id': TYPE_ID.split('/')[1],
                           'annotation_type': 'moment', 'spec': None,
                           'measurement_spec': None, 'tags': []})
    api.fulcra_api.side_effect = transport
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    return api


@pytest.mark.asyncio
async def test_tool_description_only_verified_and_noop(api):
    fn = getattr(tools, 'set_mesh_identifier')
    original = dict(api.entry)
    result = json.loads(await fn(TYPE_ID, 'Travel'))
    assert result['identifier'] == 'Travel' and result['changed'] is True
    assert api.entry == {**original, 'description': helper().write_mesh_identifier(original['description'], 'Travel')}
    api.update_data_type.assert_not_called()
    writes = [c for c in api.fulcra_api.call_args_list if c.kwargs['method'] == 'PUT']
    assert len(writes) == 1
    assert writes[0].kwargs['data'] == {'name': original['name'], 'description': api.entry['description'],
                                      'annotation_type': 'moment', 'spec': None, 'measurement_spec': None, 'tags': []}
    assert api.resolve_data_type.call_count == 2
    for call in api.resolve_data_type.call_args_list:
        assert call.kwargs == {'fulcra_userid': 'own'}
    result = json.loads(await fn(TYPE_ID, 'Travel'))
    assert result['changed'] is False
    assert api.resolve_data_type.call_count == 4
    assert sum(c.kwargs['method'] == 'PUT' for c in api.fulcra_api.call_args_list) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'fulcra_userid': 'peer'}, {'fulcra_userid': None}, {'name': 'Not mesh'}, {'id': 'MomentAnnotation/other'}, {'deprecated': True}])
async def test_tool_ownership_and_scope(api, change):
    api.entry.update(change)
    result = await getattr(tools, 'set_mesh_identifier')(TYPE_ID, 'Travel')
    assert 'verified' not in result.lower()
    api.update_data_type.assert_not_called()


@pytest.mark.asyncio
async def test_tool_ambiguous_resolution_and_malformed_marker(api):
    api.resolve_data_type.side_effect = lambda *a, **kw: [dict(api.entry), dict(api.entry)]
    assert 'ambiguous' in (await getattr(tools, 'set_mesh_identifier')(TYPE_ID, 'Travel')).lower()
    api.update_data_type.assert_not_called()
    api.resolve_data_type.side_effect = lambda *a, **kw: [dict(api.entry)]
    api.entry['description'] = 'Prose [mesh_identifier: bad]'
    assert 'malformed' in (await getattr(tools, 'set_mesh_identifier')(TYPE_ID, 'Travel')).lower()
    api.update_data_type.assert_not_called()


@pytest.mark.asyncio
async def test_tool_readback_mismatch_is_not_success(api):
    original_transport = api.fulcra_api.side_effect
    api.fulcra_api.side_effect = lambda path, **kw: original_transport(path, **{**kw, 'method': 'GET'})
    result = await getattr(tools, 'set_mesh_identifier')(TYPE_ID, 'Travel')
    assert 'could not verify' in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['MomentAnnotation/not-a-uuid', 'Event/12345678-1234-4234-8234-123456789abc', '12345678-1234-4234-8234-123456789abc'])
async def test_tool_rejects_invalid_id_without_lookup(api, value):
    await getattr(tools, 'set_mesh_identifier')(value, 'Travel')
    api.resolve_data_type.assert_not_called()
    api.update_data_type.assert_not_called()


@pytest.mark.asyncio
async def test_tool_requires_auth(monkeypatch):
    from fastmcp.exceptions import ToolError
    def denied():
        raise ToolError('not connected')
    monkeypatch.setattr(tools, 'get_fulcra_object', denied)
    with pytest.raises(ToolError, match='not connected'):
        await getattr(tools, 'set_mesh_identifier')(TYPE_ID, 'Travel')

import pytest


def helper():
    return importlib.import_module('fulcra_mcp.mesh_identifier')


def test_marker_roundtrip_preserves_prose_and_json():
    h = helper()
    prose = 'Original prose [brackets] "quoted"\n  unchanged. '
    label = 'Trip  ["Paris"] \\ café'
    description = h.write_mesh_identifier(prose, label)
    assert description.startswith(prose)
    assert h.parse_mesh_identifier(description) == label
    assert h.write_mesh_identifier(description, label) == description
    assert h.write_mesh_identifier(description, 'New').startswith(prose)
    # The catalog historically normalizes all whitespace.
    import re
    assert h.parse_mesh_identifier(re.sub(r'\s+', ' ', description).strip()) == label


@pytest.mark.parametrize('label', ['', ' ', ' x', 'x ', 'x\ny', 'x\ty', 'x\x00y', 'x\x7fy', 'x\u2028y', 'x\u200ey', 'x' * 81])
def test_invalid_identifiers(label):
    with pytest.raises(ValueError):
        helper().write_mesh_identifier('prose', label)


@pytest.mark.parametrize('description', ['[mesh_identifier: bad]', '[mesh_identifier: "a"] trailing', '[mesh_identifier: "a"] [mesh_identifier: "b"]', '[mesh_identifier: "unterminated]', '[mesh_identifier: 12]', '[mesh_identifier: ""]', '[mesh_identifier "bad"]'])
def test_malformed_ambiguous_fail_closed(description):
    with pytest.raises(ValueError):
        helper().write_mesh_identifier(description, 'New')
    with pytest.raises(ValueError):
        helper().parse_mesh_identifier(description)


def test_catalog_normalization_keeps_exact_marker_value():
    label = 'Trip  ["Paris"]'
    raw = 'Prose\n  folded.\n[mesh_identifier: ' + json.dumps(label) + ']'
    slim = tools._slim_entry({'id': TYPE_ID, 'description': raw})
    assert helper().parse_mesh_identifier(slim['description']) == label
    assert slim['description'].startswith('Prose folded. ')
    malformed = 'Prose [mesh_identifier: "bad\nlabel"]'
    # Do not turn an invalid marker into a valid label by normalizing it.
    assert tools._slim_entry({'id': TYPE_ID, 'description': malformed})['description'] == malformed


def test_marker_limits_and_embedded_marker_text():
    h = helper()
    for value in ['x' * 80, '🦊' * 80, '[mesh_identifier: "nested"]']:
        assert h.parse_mesh_identifier(h.write_mesh_identifier(None, value)) == value
    assert h.parse_mesh_identifier('ordinary prose') is None
