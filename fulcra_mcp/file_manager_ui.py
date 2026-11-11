"""The file manager panel (an MCP App) that ``open_file_manager`` shows.

Plain HTML and JavaScript speaking the MCP Apps postMessage protocol directly,
so it needs no build step and no external scripts. It talks only to the host,
which relays to this server:

* ``tools/call list_files`` to browse folders;
* ``tools/call start_file_upload`` / ``upload_file_chunk`` to upload, in chunks;
* ``resources/read fulcra://files/...`` and ``ui/download-file`` to download,
  or ``read_file(as_link=True)`` and ``ui/open-link`` where the host can't
  download files itself or the file is too large for one message.

The panel is ``fulcra_mcp/ui/file-manager/v<N>.html``, one file per version.
Hosts store the panel's URI when a connector or plugin is published, so a
released version is never edited or removed. To change the panel, copy the
current file to the next number, edit the copy and raise FILE_MANAGER_VERSION:
see "UI versions" in docs/contacts-app.md.
"""

from . import ui_versions

FILE_MANAGER_VERSION = 4
FILE_MANAGER_BUNDLES = ui_versions.bundles("file-manager")
if FILE_MANAGER_VERSION not in FILE_MANAGER_BUNDLES:
    raise RuntimeError(f"fulcra_mcp/ui/file-manager/v{FILE_MANAGER_VERSION}.html is missing.")
FILE_MANAGER_HTML = FILE_MANAGER_BUNDLES[FILE_MANAGER_VERSION].read_text(encoding="utf-8")
