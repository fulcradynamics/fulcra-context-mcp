"""Native composer mentions, independent of the packaged UI presentation."""

import json
import re
from urllib.parse import quote

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from fastmcp.resources.resource import ResourceContent, ResourceResult
from fastmcp.tools.tool import ToolResult

from .tools import get_data_catalog, list_shares
from .mesh_identifier import parse_mesh_identifier

mentions_mcp = FastMCP("Fulcra Mesh mentions")


def _direct_recipient(share):
    recipients = share.get("with_user_ids")
    if (share.get("share_all_data") is False and not share.get("group_id")
            and all(k not in share or share[k] == [] for k in ("with_group_ids", "file_paths", "file_history_paths"))
            and isinstance(share.get("data_types"), list) and len(share["data_types"]) == 1
            and isinstance(recipients, list) and len(recipients) == 1
            and isinstance(recipients[0], str)):
        return recipients[0]
    return None


async def _discover_threads() -> dict[str, str]:
    # These helpers use the existing request-scoped credentials in both transports.
    # Never retain account discovery or turn an upstream failure into empty success.
    try:
        catalog = json.loads((await get_data_catalog(name="Mesh Outbox")).removeprefix(
            "Available data types, grouped by compatible tool: "))
        shares = json.loads((await list_shares(direction="both")).removeprefix("Shares: "))
        return _thread_labels(catalog, shares)
    except ToolError:
        raise  # Preserve the existing reconnect/sign-in guidance.
    except Exception:
        raise ToolError("Mesh thread discovery failed; retry after checking the connection.") from None


def _thread_labels(catalog: dict, shares: dict) -> dict[str, str]:
    # Keep identity/discovery rules in parity with web/meshes.js. Names are labels only.
    own = shares["own_fulcra_userid"]
    if not isinstance(own, str) or not own:
        raise ValueError("Missing own identity")
    peers = {}
    for group, entries in catalog.items():
        if not group.startswith("data types usable with: ") or "get_records" not in group.removeprefix("data types usable with: ").split(" | "):
            continue
        for entry in entries:
            if not (isinstance(entry.get("id"), str) and isinstance(entry.get("name"), str)
                    and ("fulcra_userid" not in entry or isinstance(entry["fulcra_userid"], str))):
                raise ValueError("Invalid catalog identity")
            if not entry["id"].startswith("MomentAnnotation/") or not re.search(r"\bmesh outbox\b", entry["name"], re.I | re.ASCII):
                continue
            peer = entry.get("fulcra_userid") or own
            outgoing = peer == own
            if outgoing:
                covering = [s for s in shares["outgoing"] if s.get("share_all_data") is True
                            or entry["id"] in s.get("data_types", [])]
                recipients = [_direct_recipient(s) for s in covering]
                if not recipients or any(not p or p == own or p != recipients[0] for p in recipients):
                    continue
                peer = recipients[0]
            candidates = peers.setdefault(peer, [])
            try:
                identifier = parse_mesh_identifier(entry.get("description"))
            except ValueError:
                identifier = None  # Like the UI, ignore malformed display metadata.
            if identifier:
                candidates.append((0 if outgoing else 1, entry["id"], identifier))
    threads = {}
    for peer in sorted(peers):
        # Match web/mesh-identifier.js: own/outgoing first, then exact type ID.
        identifier = min(peers[peer], key=lambda candidate: candidate[:2])[2] if peers[peer] else None
        threads[peer] = f"{identifier} ({peer})" if identifier else peer
    return threads


@mentions_mcp.tool(
    title="Search Mesh mentions",
    meta={"ui": {"visibility": ["app"]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
async def mesh_mentions_search(query: str) -> ToolResult:
    """Find Mesh opening actions for the composer without reading messages."""
    threads = await _discover_threads()
    items = [{"type": "resource_link", "uri": "mesh://threads",
              "name": "List Meshes", "title": "List Meshes", "mimeType": "application/json",
              "description": "Open the clickable mesh list in chat with mesh_threads_open({})."}]
    items += [
        {"type": "resource_link", "uri": "mesh://threads/id-" + quote(peer, safe=""),
         "name": f"Open Mesh: {title}", "title": f"Open Mesh: {title}",
         "mimeType": "application/json",
         "description": "Open this exact peer's thread with mesh_conversation_open; resolve this reference for its peer ID."}
        for peer, title in threads.items() if query.strip().casefold() in title.casefold()
    ][:20]
    return ToolResult(content=[], structured_content={"items": items})


@mentions_mcp.resource("mesh://threads", mime_type="application/json")
def mesh_list_descriptor() -> dict:
    """Describe the list-opening action, not account data or an HTML attachment."""
    return {"title": "List Meshes",
            "open_tool": {"name": "mesh_threads_open", "arguments": {}}}


@mentions_mcp.resource("mesh://threads/id-{peer}", mime_type="application/json")
async def mesh_thread_descriptor(peer: str) -> ResourceResult:
    """Revalidate a referenced exact peer; return identity only, never message history."""
    # FastMCP decodes the template parameter once. Do not unquote it again.
    threads = await _discover_threads()
    if peer not in threads:
        raise ResourceError("Mesh thread is not available to this account.")
    return ResourceResult([ResourceContent(
        json.dumps({"peer_fulcra_userid": peer, "title": threads[peer],
                    "open_tool": {"name": "mesh_conversation_open",
                                  "arguments": {"peer_fulcra_userid": peer}}}),
        mime_type="application/json",
    )])
