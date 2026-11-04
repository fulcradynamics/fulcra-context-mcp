"""Public catalog results differ only on the standard endpoint."""
import json
import urllib.error

import pytest
from fastmcp import Client
from fulcra_mcp import tools
from fulcra_mcp.endpoint import create_server
from fulcra_mcp.openai_endpoint import create_openai_server


@pytest.mark.parametrize('openai_first', [False, True])
@pytest.mark.parametrize('lookup', [False, True])
@pytest.mark.parametrize('shared', [False, True])
async def test_creation_timestamp_endpoint_isolation(fake_fulcra, openai_first, lookup, shared):
    identifier = 'Event/00000000-0000-4000-8000-000000000001'
    created = '2026-10-06T18:36:13.130916Z'
    owner = '00000000-0000-4000-8000-000000000002'
    entry = {'id': identifier, 'api_version': 'v1',
             'categories': ['user_defined'] + (['shared_type'] if shared else []),
             'fulcra_userid': owner, 'metadata': {'created_at': created, 'private': 'omit'}}
    fake_fulcra.v1_catalog.return_value = [entry]
    fake_fulcra.v1_catalog_schema.return_value = {'type': 'object', 'properties': {}}
    factories = [(create_server, True), (create_openai_server, False)]
    if openai_first:
        factories.reverse()
    args = {'data_type': identifier} if lookup else {}
    if shared:
        args['fulcra_userid'] = owner
    for factory, standard in factories * 2 + [(lambda: tools.tools_mcp, True)]:
        async with Client(factory()) as client:
            await client.list_tools()
            result = await client.call_tool('get_data_catalog', args)
        text = result.content[0].text
        [actual] = [row for group in json.loads(text[text.index('{'):]).values() for row in group]
        expected = {'id': identifier, 'categories': entry['categories']}
        if shared:
            expected['fulcra_userid'] = owner
        if standard:
            expected['created_at'] = created
        assert actual == expected
    assert entry['metadata'] == {'created_at': created, 'private': 'omit'}


@pytest.mark.parametrize('metadata', [None, {}, {'created_at': None}])
async def test_missing_creation_timestamp_is_not_invented(fake_fulcra, metadata):
    fake_fulcra.v1_catalog.return_value = [{'id': 'Event', 'api_version': 'v1', 'metadata': metadata}]
    for factory in (create_server, create_openai_server):
        async with Client(factory()) as client:
            result = await client.call_tool('get_data_catalog', {})
        assert 'created_at' not in result.content[0].text


@pytest.mark.parametrize('status', [401, 403, 500])
async def test_catalog_errors_remain_identical(fake_fulcra, status):
    fake_fulcra.v1_catalog.side_effect = urllib.error.HTTPError(
        'https://example.invalid/catalog', status, 'test error', {}, None)
    results = []
    for factory in (create_server, create_openai_server):
        async with Client(factory()) as client:
            result = await client.call_tool('get_data_catalog', {}, raise_on_error=False)
            results.append((result.is_error, result.content))
    assert results[0] == results[1]
