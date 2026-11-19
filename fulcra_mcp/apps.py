"""Agents I Know MCP App; host navigation stays in registration metadata."""

from pathlib import Path
from urllib.parse import quote

from fastmcp import FastMCP

from mcp.types import Icon
from fulcra_mcp import ui_versions
from fulcra_mcp.settings import settings

app_mcp = FastMCP("Agents I Know UI")
# Embed SVG icon as data URI (like Bits and Bolts) for instant loading
STATIC_DIR = Path(__file__).parent / "static"
MENU_ICONS = [
    Icon(
        src="data:image/svg+xml," + quote((STATIC_DIR / "menu-icon.svg").read_text(encoding="utf-8")),
        mimeType="image/svg+xml",
        sizes=["any"]
    )
]
# The version tools advertise. web/ui-version.js reads this line to name the
# bundle it builds. Every UI update should raise the version number.
# see "UI versions" in docs/contacts-app.md.
CONTACTS_UI_VERSION = 84
UI_MIME_TYPE = "text/html;profile=mcp-app"
FULL_PANEL = {"openai/ui": {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]}}
# Every version ever released, current included. Earlier ones stay readable for
# hosts that stored their URIs (ui_versions.py).
CONTACTS_BUNDLES = ui_versions.bundles("contacts")
if CONTACTS_UI_VERSION not in CONTACTS_BUNDLES:
    raise RuntimeError(f"fulcra_mcp/ui/contacts/v{CONTACTS_UI_VERSION}.html is missing; run `npm run build` in web/.")


def contacts_uris(version: int) -> tuple[str, str, str]:
    """A version's global, thread and direct-resource URIs."""
    thread = f"ui://fulcra/contacts/thread/v{version}.html"
    return f"ui://fulcra/contacts/v{version}.html", thread, thread + "?startup=resource"


UI_URI, THREAD_UI_URI, CONTACTS_UI_URI = contacts_uris(CONTACTS_UI_VERSION)


def contacts_html_for(version: int, presentation: str = "global", startup_resource: bool = False) -> str:
    """One bundle serves all three URIs; only these meta values differ."""
    html = CONTACTS_BUNDLES[version].read_text(encoding="utf-8")
    html = html.replace('<meta name="connection-debug" content="false">',
                        f'<meta name="connection-debug" content="{str(settings.fulcra_contacts_debug).lower()}">', 1)
    html = html.replace('<meta name="connection-presentation" content="global">',
                        f'<meta name="connection-presentation" content="{presentation}">', 1)
    if startup_resource:
        html = html.replace('</head>', '<meta name="connection-startup" content="resource"></head>', 1)
    return html


@app_mcp.tool(
    icons=MENU_ICONS,
    title="Agent Contacts",
    app={"resourceUri": THREAD_UI_URI, "visibility": ["model", "app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "thread"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def open_agent_contacts(peer_fulcra_userid: str | None = None, thread_id: str | None = None) -> dict:
    """Open the Agents I Know panel for the user to review and manage their contacts manually.
    To prepare invitations, send messages, or check messages directly in chat,
    use the Fulcra skills when available.
    Read-only. For an exact contact, resolve contacts://threads/id- and pass its
    exact peer_fulcra_userid or discovered multiparty thread_id. Names are not IDs.
    """
    if peer_fulcra_userid is not None and not peer_fulcra_userid.strip():
        raise ValueError("Provide a nonblank exact peer user ID or omit it.")
    if thread_id is not None:
        if peer_fulcra_userid is not None or not thread_id.startswith('connection:'):
            raise ValueError('Use one exact discovered thread_id or peer user ID, not both.')
        return {"presentation": "thread", "thread_id": thread_id}
    return {"presentation": "thread", "peer_fulcra_userid": peer_fulcra_userid}


@app_mcp.resource(THREAD_UI_URI, mime_type=UI_MIME_TYPE, meta=FULL_PANEL)
def thread_html() -> str:
    """Same full-panel renderer; startup waits for the optional exact target."""
    return contacts_html_for(CONTACTS_UI_VERSION, "thread")


@app_mcp.resource(CONTACTS_UI_URI, mime_type=UI_MIME_TYPE, meta=FULL_PANEL)
def contacts_html() -> str:
    """Direct-resource list: no invoking tool result is required for startup."""
    return contacts_html_for(CONTACTS_UI_VERSION, "thread", startup_resource=True)


@app_mcp.tool(
    icons=MENU_ICONS,
    title="Agents I Know",
    app={"resourceUri": UI_URI, "visibility": ["app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "global"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def open_agent_contacts_home() -> dict[str, str]:
    """Open Agents I Know, selecting the first available contact read-only."""
    return {"message": "Agents I Know is ready."}


@app_mcp.resource(UI_URI, mime_type=UI_MIME_TYPE, meta=FULL_PANEL)
def contacts_html_bundle() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    return contacts_html_for(CONTACTS_UI_VERSION)


def _earlier(version: int, *variant):
    return lambda: contacts_html_for(version, *variant)


for _version in sorted(CONTACTS_BUNDLES.keys() - {CONTACTS_UI_VERSION}):
    for _uri, _variant in zip(contacts_uris(_version), [(), ("thread",), ("thread", True)]):
        ui_versions.keep_readable(app_mcp, _uri, _earlier(_version, *_variant),
                                  mime_type=UI_MIME_TYPE, meta=FULL_PANEL)
app_mcp.add_middleware(ui_versions.CurrentVersionsOnly())
