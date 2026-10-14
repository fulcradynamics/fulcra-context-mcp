"""Native composer mentions, independent of the packaged UI presentation."""

import json
import re
from importlib.resources import files
from urllib.parse import quote

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from fastmcp.resources.resource import ResourceContent, ResourceResult
from fastmcp.tools.tool import ToolResult

from .tools import get_data_catalog, list_shares
from .contact_identifier import parse_contact_identifier
from .connection_compatibility import SHARE_NAME_PREFIX, CHANNEL_PREFIXES

mentions_mcp = FastMCP("Agents I Know mentions")
CHANNEL_SCHEMA = json.loads(files('fulcra_mcp').joinpath('static/connection-schema.json').read_text())


def _semantic(value, key=None):
    if isinstance(value, list):
        return sorted(value) if key in ('enum', 'required', 'required_fields') else [_semantic(v) for v in value]
    if isinstance(value, dict):
        return {k: _semantic(v, k) for k, v in value.items() if k not in ('description', 'title', 'default')}
    return value


def _compatible_schema(entry):
    return _semantic({'fields': {k: entry.get('fields', {}).get(k) for k in CHANNEL_SCHEMA['fields']},
                      'required_fields': entry.get('required_fields')}) == _semantic(CHANNEL_SCHEMA)


def _direct_recipient(share):
    recipients = share.get("with_user_ids")
    if (share.get("share_all_data") is False and not share.get("group_id")
            and not share.get('time_start') and not share.get('time_end')
            and share.get('datashare_name', '').startswith(SHARE_NAME_PREFIX)
            and all(k not in share or share[k] == [] for k in ("with_group_ids", "file_paths", "file_history_paths"))
            and isinstance(share.get("data_types"), list) and len(share["data_types"]) == 1
            and isinstance(recipients, list) and recipients
            and all(isinstance(p, str) and p for p in recipients)):
        return recipients
    return None


async def _discover_threads() -> dict[str, str]:
    # These helpers use the existing request-scoped credentials in both transports.
    # Never retain account discovery or turn an upstream failure into empty success.
    try:
        catalog = json.loads((await get_data_catalog()).removeprefix(
            "Available data types, grouped by compatible tool: "))
        shares = json.loads((await list_shares(direction="both")).removeprefix("Shares: "))
        for entries in catalog.values():
            for entry in entries:
                if not entry.get('fields') and entry.get('id', '').startswith('Event/') and entry.get('description', '').startswith(CHANNEL_PREFIXES):
                    exact = json.loads((await get_data_catalog(data_type=entry['id'],
                        fulcra_userid=entry.get('fulcra_userid') or shares['own_fulcra_userid'])).removeprefix(
                            'Available data types, grouped by compatible tool: '))
                    matches = [e for group in exact.values() for e in group if e.get('id') == entry['id']
                               and e.get('fulcra_userid', shares['own_fulcra_userid']) == entry.get('fulcra_userid', shares['own_fulcra_userid'])]
                    schema = matches[0] if len(matches) == 1 else {}
                    entry['fields'] = schema.get('fields', {})
                    entry['required_fields'] = schema.get('required_fields', [])
        return _thread_labels(catalog, shares)
    except ToolError:
        raise  # Preserve the existing reconnect/sign-in guidance.
    except Exception:
        raise ToolError("Agent Contact thread discovery failed; retry after checking the connection.") from None


def _thread_labels(catalog: dict, shares: dict) -> dict[str, str]:
    # Keep identity/discovery rules in parity with web/connections-discovery.js. Names are labels only.
    own = shares["own_fulcra_userid"]
    if not isinstance(own, str) or not own:
        raise ValueError("Missing own identity")
    peers = {}
    for group, entries in catalog.items():
        if not group.startswith("data types usable with: ") or "get_records" not in group.removeprefix("data types usable with: ").split(" | "):
            continue
        for entry in entries:
            if not (isinstance(entry.get("id"), str)
                    and ("name" not in entry or isinstance(entry["name"], str))
                    and ("fulcra_userid" not in entry or isinstance(entry["fulcra_userid"], str))):
                raise ValueError("Invalid catalog identity")
            if (not entry['id'].startswith('Event/')
                    or not entry.get('description', '').startswith(CHANNEL_PREFIXES)
                    or not _compatible_schema(entry)):
                continue
            peer = entry.get("fulcra_userid") or own
            outgoing = peer == own
            if outgoing:
                covering = [s for s in shares["outgoing"] if s.get("share_all_data") is True
                            or any(t in s.get('data_types', []) for t in (entry['id'], 'Event', 'Event/*', '*'))]
                grants = [_direct_recipient(s) if s.get('data_types') == [entry['id']] else None for s in covering]
                if not grants or any(not g for g in grants):
                    continue
                recipients = sorted({p for g in grants for p in g})
                if own in recipients or len(recipients) > 32:
                    continue
                peer = recipients[0] if len(recipients) == 1 else 'connection:' + json.dumps(sorted([own, *recipients]), separators=(',', ':'))
            elif not any(s.get('sharing_fulcra_userid') == peer and s.get('grant_type') == 'user'
                         and s.get('datashare_name', '').startswith(SHARE_NAME_PREFIX)
                         and not any(s.get(k) for k in ('share_all_data', 'group_id', 'time_start', 'time_end'))
                         and s.get('data_types') == [entry['id']] for s in shares['incoming']):
                continue
            candidates = peers.setdefault(peer, [])
            try:
                identifier = parse_contact_identifier(entry.get("description"))
            except ValueError:
                identifier = None  # Like the UI, ignore malformed display metadata.
            if identifier:
                candidates.append((0 if outgoing else 1, entry["id"], identifier))
    threads = {}
    for peer in sorted(peers):
        # Match web/contact-identifier.js: own/outgoing first, then exact type ID.
        identifier = min(peers[peer], key=lambda candidate: candidate[:2])[2] if peers[peer] else None
        if peer.startswith('connection:'):
            people = json.loads(peer.removeprefix('connection:'))
            labels = []
            for person in people:
                names = {s.get('sharing_fulcra_user_name') for s in shares['incoming']
                         if s.get('sharing_fulcra_userid') == person and isinstance(s.get('sharing_fulcra_user_name'), str) and s['sharing_fulcra_user_name'].strip()}
                name = 'You' if person == own else next(iter(names)) if len(names) == 1 else person
                labels.append(f'{name} ({person})' if name != person else person)
            threads[peer] = (f'{identifier} — ' if identifier else 'Multiparty — ') + ', '.join(labels)
        else:
            threads[peer] = f"{identifier} ({peer})" if identifier else peer
    return threads


@mentions_mcp.tool(
    title="Search Agent Contact mentions",
    meta={"ui": {"visibility": ["app"]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
async def agent_contacts_search(query: str) -> ToolResult:
    """Find Agent Contact opening actions for the composer without reading messages."""
    threads = await _discover_threads()
    items = [{"type": "resource_link", "uri": "contacts://threads",
              "name": "Agents I Know", "title": "Agents I Know", "mimeType": "application/json",
              "description": "Open the clickable connection list in chat with agent_contacts_open({})."}]
    items += [
        {"type": "resource_link", "uri": "contacts://threads/id-" + quote(peer, safe=""),
         "name": f"Open Agent Contact: {title}", "title": f"Open Agent Contact: {title}",
         "mimeType": "application/json",
         "description": "Open this exact thread with agent_contact_open; resolve this reference for its peer ID or multiparty thread_id."}
        for peer, title in threads.items() if query.strip().casefold() in title.casefold()
    ][:20]
    return ToolResult(content=[], structured_content={"items": items})


@mentions_mcp.resource("contacts://threads", mime_type="application/json")
def contact_list_descriptor() -> dict:
    """Describe the list-opening action, not account data or an HTML attachment."""
    return {"title": "Agents I Know",
            "open_tool": {"name": "agent_contacts_open", "arguments": {}}}


@mentions_mcp.resource("contacts://threads/id-{peer}", mime_type="application/json")
async def contact_thread_descriptor(peer: str) -> ResourceResult:
    """Revalidate a referenced exact peer; return identity only, never message history."""
    # FastMCP decodes the template parameter once. Do not unquote it again.
    threads = await _discover_threads()
    if peer not in threads:
        raise ResourceError("Agent Contact thread is not available to this account.")
    return ResourceResult([ResourceContent(
        json.dumps({"thread_id" if peer.startswith('connection:') else "peer_fulcra_userid": peer, "title": threads[peer],
                    "open_tool": {"name": "agent_contact_open",
                                  "arguments": {"thread_id" if peer.startswith('connection:') else "peer_fulcra_userid": peer}}}),
        mime_type="application/json",
    )])
