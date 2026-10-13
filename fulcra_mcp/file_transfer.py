"""Moving whole files, including large and binary ones, between Fulcra and the
client, without passing their bytes through the model.

* **Resources.** ``fulcra://files/{path}`` (and, for files another user shares,
  ``fulcra://users/{fulcra_userid}/files/{path}``) serve a file's bytes through
  ``resources/read``.
* **The file manager panel** (an MCP App, ``ui://fulcra/file-manager.html``).
  In hosts that display MCP Apps, ``open_file_manager`` shows a panel where the
  user browses folders, drops files in to upload them and downloads files. The
  panel uploads in chunks through two app-only tools, ``start_file_upload`` and
  ``upload_file_chunk``, which feed a resumable upload to Fulcra's storage. It
  downloads through ``resources/read`` and the host's ``ui/download-file``, or a
  download link where the host can't do that.
* **Download links** (``get_file_download_link``), for any client: a short-lived
  link the user opens in a browser. ``main.py`` serves ``/files/download/<token>``.

Clients without MCP Apps still list the app-only tools (the protocol doesn't let
a server vary its tool list by client), so their descriptions say what to use
instead.
"""

import base64
import binascii
import functools
import hashlib
import json
import mimetypes
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

import structlog
from fastmcp.apps.config import AppConfig
from fastmcp.exceptions import ResourceError, ToolError
from fastmcp.resources import ResourceContent
from fastmcp.utilities.mime import UI_MIME_TYPE

from . import tools
from .credentials import current_grant_id
from .file_manager_ui import FILE_MANAGER_HTML
from .settings import settings
from .tools import _file_path, _friendly_http_errors, _slim_file, tools_mcp

logger = structlog.getLogger(__name__)

FILE_MANAGER_URI = "ui://fulcra/file-manager.html"

# Resumable uploads take chunks in multiples of 256 KiB, except the last.
UPLOAD_GRANULE = 256 * 1024
UPLOAD_CHUNK_BYTES = 8 * UPLOAD_GRANULE  # 2 MiB: what the panel sends
MAX_UPLOAD_CHUNK_BYTES = 32 * UPLOAD_GRANULE  # 8 MiB: the most one call takes
MAX_UPLOAD_BYTES = 2 * 1024**3
UPLOAD_TTL_SECONDS = 24 * 3600

# resources/read carries the whole file, base64-encoded, in one message.
MAX_RESOURCE_BYTES = 20 * 1024**2

DOWNLOAD_LINK_TTL_SECONDS = 600

# write_file's base64 mode: the model writes every character of it.
MAX_WRITE_BASE64_BYTES = 5 * 1024**2

# For agents in clients that can't show the panel.
WITHOUT_THE_PANEL = (
    "If this client can't display the file manager panel: write_file uploads "
    "text, or base64 with encoding='base64' (up to 5 MB); for larger files, "
    "use start_file_upload and upload_file_chunk, or the Fulcra CLI "
    "(`uvx fulcra-api file upload`). get_file_download_link gives the user a "
    "link to download any file. read_file reads a file's contents, including "
    "spreadsheets as CSV."
)


def file_resource_uri(path: str, fulcra_userid: str | None = None) -> str:
    """The resource URI for a file path, e.g. ``fulcra://files/docs/a%20b.xlsx``."""
    quoted = urllib.parse.quote(path.lstrip("/"))
    if fulcra_userid:
        return f"fulcra://users/{fulcra_userid}/files/{quoted}"
    return f"fulcra://files/{quoted}"


def guess_content_type(name: str, default: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(name)[0] or default


SPREADSHEET_SUFFIXES = (".xlsx", ".xlsm")


def spreadsheet_as_csv(path: str, data: bytes) -> str | None:
    """An Excel workbook as CSV text, one section per sheet; ``None`` if ``data``
    isn't one. Cells hold their last computed values, not formulas."""
    if not path.lower().endswith(SPREADSHEET_SUFFIXES):
        return None
    import csv
    import io

    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        return None
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    try:
        for sheet in workbook.worksheets:
            out.write(f"# Sheet: {sheet.title}\n")
            for row in sheet.iter_rows(values_only=True):
                writer.writerow(["" if v is None else v for v in row])
            out.write("\n")
    finally:
        workbook.close()
    return out.getvalue()


# ---------------------------------------------------------------- state store


def _record_path(kind: str, key: str) -> Path:
    """Where a record lives under the server's state directory. ``key`` may be a
    secret, so the filename is its hash."""
    digest = hashlib.sha256(key.encode()).hexdigest()
    return settings.state_path / kind / f"{digest}.json"


def _save_record(kind: str, key: str, record: dict) -> None:
    path = _record_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))


def _load_record(kind: str, key: str) -> dict | None:
    """The record, or ``None`` if it's missing or has expired."""
    path = _record_path(kind, key)
    try:
        record = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if record.get("expires_at", 0) < time.time():
        path.unlink(missing_ok=True)
        return None
    return record


def _delete_record(kind: str, key: str) -> None:
    _record_path(kind, key).unlink(missing_ok=True)


# ------------------------------------------------------------------ resources


def _read_file(path: str, fulcra_userid: str | None) -> list[ResourceContent]:
    fulcra = tools.get_fulcra_object()
    # FastMCP has already percent-decoded the template's path.
    path = _file_path(path)
    try:
        record = fulcra.resolve_filepath(path, fulcra_userid=fulcra_userid)[0]
    except Exception:
        if fulcra_userid:
            raise ResourceError(
                f"User {fulcra_userid} doesn't share a file at {path!r} with this user."
            )
        raise ResourceError(f"No file at {path!r}. list_files shows what's there.")
    size = record.get("size") or 0
    if size > MAX_RESOURCE_BYTES:
        raise ResourceError(
            f"{path} is {size} bytes, too large to read in one message (the most "
            f"is {MAX_RESOURCE_BYTES}). get_file_download_link gives a link to it."
        )
    data = fulcra.download_file(record["id"], fulcra_userid=fulcra_userid).read()
    mime_type = guess_content_type(record.get("name") or path)
    if _is_text_type(mime_type):
        try:
            return [ResourceContent(data.decode("utf-8"), mime_type=mime_type)]
        except UnicodeDecodeError:
            pass
    return [ResourceContent(data, mime_type=mime_type)]


def _is_text_type(mime_type: str) -> bool:
    return mime_type.startswith("text/") or mime_type in (
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-yaml",
    )


@tools_mcp.resource(
    "fulcra://files/{path*}",
    name="Fulcra file",
    description="A file in the user's Fulcra account, by its path.",
)
def file_resource(path: str) -> list[ResourceContent]:
    return _read_file(path, None)


@tools_mcp.resource(
    "fulcra://users/{fulcra_userid}/files/{path*}",
    name="Shared Fulcra file",
    description="A file another Fulcra user shares with this user.",
)
def shared_file_resource(fulcra_userid: str, path: str) -> list[ResourceContent]:
    return _read_file(path, fulcra_userid)


@tools_mcp.resource(
    FILE_MANAGER_URI,
    name="Fulcra file manager",
    description="The panel open_file_manager shows.",
    mime_type=UI_MIME_TYPE,
    app=AppConfig(prefers_border=True),
)
def file_manager_ui() -> str:
    return FILE_MANAGER_HTML


# ----------------------------------------------------------- the file manager


def _raising_http_errors(func):
    """Like ``_friendly_http_errors``, but for tools that return structured
    results: the friendly message is raised as a tool error, not returned."""
    friendly = _friendly_http_errors(func)

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        result = await friendly(*args, **kwargs)
        if isinstance(result, str):
            raise ToolError(result)
        return result

    return wrapper



@tools_mcp.tool(
    annotations={"title": "Open File Manager", "readOnlyHint": True},
    app=AppConfig(resource_uri=FILE_MANAGER_URI),
)
@_friendly_http_errors
async def open_file_manager(path: str = "/") -> str:
    """Show the user a file manager for their Fulcra files, where they can
    upload files from their computer (any type or size, such as spreadsheets)
    and download files. Use it when the user wants to upload or download files.

    Args:
        path: The folder to open (default "/").
    """
    fulcra = tools.get_fulcra_object()
    path = _file_path(path)
    listing = fulcra.list_files(path)
    result = {
        "folders": listing.get("folders") or [],
        "files": [_slim_file(f) for f in listing.get("files") or []],
    }
    return (
        f"Showing the Fulcra file manager at {path}. Files the user uploads "
        "there appear in list_files. "
        + WITHOUT_THE_PANEL
        + f" Files at {path}: "
        + json.dumps(result)
    )


def _require_grant() -> str:
    grant_id = current_grant_id()
    if grant_id is None:
        raise ToolError("This session isn't connected to a Fulcra account.")
    return grant_id


@tools_mcp.tool(
    annotations={"title": "Start File Upload", "destructiveHint": False},
    app=AppConfig(resource_uri=FILE_MANAGER_URI, visibility=["app"]),
)
@_raising_http_errors
async def start_file_upload(
    path: str, size: int, content_type: str | None = None
) -> dict:
    """Start uploading a file of any type or size, in chunks. Used by the file
    manager panel; agents can use it too. Then send the file's bytes, in order,
    with upload_file_chunk. For small text files, write_file is simpler.

    Args:
        path: The full path to write to, e.g. "/reports/q3.xlsx". An existing
            file at that path gets a new version.
        size: The file's size in bytes.
        content_type: Its MIME type; guessed from the name when left out.
    Returns:
        The upload_id, and the chunk size to use: every chunk but the last must
        be a multiple of 256 KiB.
    """
    grant_id = _require_grant()
    path = _file_path(path)
    name = PurePosixPath(path).name
    if not name:
        raise ToolError("path must end in a file name, e.g. /reports/q3.xlsx.")
    if size < 0 or size > MAX_UPLOAD_BYTES:
        raise ToolError(f"size must be between 0 and {MAX_UPLOAD_BYTES} bytes.")
    content_type = content_type or guess_content_type(name)

    fulcra = tools.get_fulcra_object()
    response = json.loads(
        fulcra.fulcra_api(
            "/input/v1/file_upload",
            method="POST",
            data={
                "content_length": size,
                "content_type": content_type,
                "name": name,
                "path": str(PurePosixPath(path).parent),
            },
        )
    )
    upload_id = secrets.token_urlsafe(16)
    _save_record(
        "uploads",
        upload_id,
        {
            "grant_id": grant_id,
            "url": response["url"],
            "path": path,
            "size": size,
            "received": 0,
            "file": _slim_file(response.get("file") or {}),
            "expires_at": time.time() + UPLOAD_TTL_SECONDS,
        },
    )
    logger.info("file_upload_started", path=path, size=size)
    return {
        "upload_id": upload_id,
        "path": path,
        "size": size,
        "chunk_size": UPLOAD_CHUNK_BYTES,
    }


def _put_chunk(url: str, data: bytes, start: int, total: int) -> int:
    """Send one chunk of a resumable upload. Returns how many bytes storage has
    now committed; ``total`` once the upload is complete."""
    if data:
        content_range = f"bytes {start}-{start + len(data) - 1}/{total}"
    else:
        content_range = f"bytes */{total}"
    request = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Content-Length": str(len(data)), "Content-Range": content_range},
    )
    try:
        with urllib.request.urlopen(request):
            return total
    except urllib.error.HTTPError as e:
        if e.code != 308:
            raise
        # 308 Resume Incomplete: Range says what storage has so far.
        committed = e.headers.get("Range")
        e.close()
        return int(committed.rsplit("-", 1)[1]) + 1 if committed else 0


@tools_mcp.tool(
    annotations={"title": "Upload File Chunk", "destructiveHint": False},
    app=AppConfig(resource_uri=FILE_MANAGER_URI, visibility=["app"]),
)
@_raising_http_errors
async def upload_file_chunk(upload_id: str, offset: int, data: str) -> dict:
    """Send the next chunk of an upload begun with start_file_upload. Used by
    the file manager panel; agents can use it too.

    Args:
        upload_id: From start_file_upload.
        offset: Where this chunk starts in the file, in bytes; chunks go in
            order. Resending a chunk that already arrived is harmless.
        data: The chunk, base64-encoded. Every chunk but the last must be a
            multiple of 256 KiB, and at most 8 MiB.
    Returns:
        How many bytes have arrived, and the file once the last chunk is in.
    """
    grant_id = _require_grant()
    record = _load_record("uploads", upload_id)
    if record is None or record["grant_id"] != grant_id:
        raise ToolError(
            f"No upload {upload_id!r} in progress; it may have expired. Start "
            "again with start_file_upload."
        )
    try:
        chunk = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ToolError("data must be base64.")

    size, received = record["size"], record["received"]
    end = offset + len(chunk)
    if offset < received and end <= received:
        return {"upload_id": upload_id, "received": received, "size": size, "done": False}
    if offset != received:
        raise ToolError(f"Expected the chunk starting at byte {received}, got {offset}.")
    if end > size:
        raise ToolError(f"The chunk ends at byte {end}, past the file's size ({size}).")
    if len(chunk) > MAX_UPLOAD_CHUNK_BYTES:
        raise ToolError(f"A chunk can be at most {MAX_UPLOAD_CHUNK_BYTES} bytes.")
    if end < size and len(chunk) % UPLOAD_GRANULE:
        raise ToolError(
            f"Every chunk but the last must be a multiple of {UPLOAD_GRANULE} bytes."
        )
    if not chunk and size:
        raise ToolError("The chunk is empty.")

    committed = _put_chunk(record["url"], chunk, offset, size)
    if committed >= size:
        _delete_record("uploads", upload_id)
        logger.info("file_upload_finished", path=record["path"], size=size)
        return {
            "upload_id": upload_id,
            "received": size,
            "size": size,
            "done": True,
            "path": record["path"],
            "file": record["file"],
            "resource_uri": file_resource_uri(record["path"]),
        }
    record["received"] = committed
    _save_record("uploads", upload_id, record)
    return {"upload_id": upload_id, "received": committed, "size": size, "done": False}


# ------------------------------------------------------------ download links


def _unique_local_path(folder: Path, name: str) -> Path:
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


@tools_mcp.tool(annotations={"title": "Get File Download Link", "readOnlyHint": True})
@_raising_http_errors
async def get_file_download_link(path: str, fulcra_userid: str | None = None) -> dict:
    """Give the user a way to download a file to their computer, e.g. a
    spreadsheet: a link they open in a browser. It works for 10 minutes; make a
    new one rather than reusing an old one.

    Args:
        path: The file's full path.
        fulcra_userid: Download a file another Fulcra user shares.
    """
    fulcra = tools.get_fulcra_object()
    path = _file_path(path)
    try:
        record = fulcra.resolve_filepath(path, fulcra_userid=fulcra_userid)[0]
    except Exception:
        if fulcra_userid:
            raise ToolError(
                f"User {fulcra_userid} doesn't share a file at {path!r} with this user."
            )
        raise ToolError(f"No file at {path!r}. list_files shows what's there.")
    name = record.get("name") or PurePosixPath(path).name

    if settings.fulcra_environment == "stdio":
        # This server runs on the user's computer: save the file there.
        folder = Path.home() / "Downloads"
        folder.mkdir(parents=True, exist_ok=True)
        target = _unique_local_path(folder, name)
        response = fulcra.download_file(record["id"], fulcra_userid=fulcra_userid)
        with target.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        return {
            "saved_to": str(target),
            "name": name,
            "size": record.get("size"),
            "note": "This server runs on the user's computer, so the file was saved there.",
        }

    token = secrets.token_urlsafe(32)
    expires_at = time.time() + DOWNLOAD_LINK_TTL_SECONDS
    _save_record(
        "download_links",
        token,
        {
            "grant_id": _require_grant(),
            "file_id": record["id"],
            "fulcra_userid": fulcra_userid,
            "name": name,
            "expires_at": expires_at,
        },
    )
    url = f"{settings.oidc_server_url.rstrip('/')}/files/download/{token}"
    return {
        "url": url,
        "name": name,
        "size": record.get("size"),
        "expires_in_seconds": DOWNLOAD_LINK_TTL_SECONDS,
        "note": "Give the user this link to open in a browser. It works for 10 minutes.",
    }


def download_link_target(token: str) -> dict | None:
    """The download a link's token stands for, or ``None`` if it's unknown or
    has expired. Used by the ``/files/download/<token>`` route."""
    return _load_record("download_links", token)
