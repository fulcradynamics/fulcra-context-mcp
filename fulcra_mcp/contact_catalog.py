"""Bulk schema projection for the contacts panel, separate from model tools."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from urllib.error import URLError

from fastmcp import FastMCP
from . import tools

catalog_mcp = FastMCP('Agent Contact Catalog')


def _catalog():
    api = tools.get_fulcra_object()
    catalog = api.v1_catalog()

    def describe(entry):
        slim = tools._slim_entry(entry)
        if entry['id'].startswith('Event/'):
            try:
                fields, required = tools._user_defined_fields(api.v1_catalog_schema(
                    entry['id'], 'v1', fulcra_userid=entry.get('fulcra_userid'),
                ))
            except (URLError, TimeoutError):
                slim['schema_error'] = True
            else:
                slim.update(fields=fields, required_fields=required)
        return slim

    candidates = {(entry.get('fulcra_userid'), entry['id']): entry for entry in catalog
                  if entry['id'].startswith(('Event/', 'MomentAnnotation/'))}
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(describe, candidates.values()))
    return 'Available data types, grouped by compatible tool: ' + json.dumps({
        'data types usable with: get_records': entries,
    })


@catalog_mcp.tool(
    app={'visibility': ['app']},
    annotations={'title': 'Get Agent Contact Catalog', 'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
)
async def get_agent_contact_catalog() -> str:
    """List contact-channel candidates with their schemas for the contacts panel."""
    return await asyncio.to_thread(_catalog)
