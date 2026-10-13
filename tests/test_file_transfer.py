"""Moving whole files: file resources, the file manager panel and its upload
tools, download links, and what read_file/write_file tell agents that can't
use them."""

import base64
import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import fulcra_mcp.file_transfer as ft
from fulcra_mcp.settings import settings

FILE = {"id": "f-1", "name": "q3.xlsx", "path": "/reports", "size": 11}


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_path", tmp_path / "state")
    return tmp_path / "state"


def _download_returns(fake_fulcra, data: bytes):
    fake_fulcra.download_file.return_value = io.BytesIO(data)


def _xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Totals"
    sheet.append(["region", "sales"])
    sheet.append(["west", 12])
    other = workbook.create_sheet("Notes")
    other.append(['say "hi", ok'])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


# --- resources -------------------------------------------------------------------


async def test_a_file_is_served_as_a_blob_resource(client, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, size=4)]
    _download_returns(fake_fulcra, b"\x00\x01\xff\xfe")

    [content] = await client.read_resource("fulcra://files/reports/q3%20final.xlsx")

    fake_fulcra.resolve_filepath.assert_called_once_with(
        "/reports/q3 final.xlsx", fulcra_userid=None
    )
    assert base64.b64decode(content.blob) == b"\x00\x01\xff\xfe"
    assert content.mimeType == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


async def test_a_resource_path_is_decoded_once(client, fake_fulcra):
    # A file literally named "literal%20name.txt" is encoded as %2520.
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="literal%20name.txt", size=2)]
    _download_returns(fake_fulcra, b"hi")

    await client.read_resource(ft.file_resource_uri("/docs/literal%20name.txt"))

    fake_fulcra.resolve_filepath.assert_called_once_with(
        "/docs/literal%20name.txt", fulcra_userid=None
    )


async def test_a_shared_file_resource_reads_as_that_user(client, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="a.txt", size=2)]
    _download_returns(fake_fulcra, b"hi")

    [content] = await client.read_resource("fulcra://users/u-2/files/notes/a.txt")

    fake_fulcra.resolve_filepath.assert_called_once_with("/notes/a.txt", fulcra_userid="u-2")
    assert content.text == "hi"


async def test_a_file_too_large_for_one_message_points_to_a_link(client, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, size=ft.MAX_RESOURCE_BYTES + 1)]

    with pytest.raises(Exception, match="get_file_download_link"):
        await client.read_resource("fulcra://files/reports/q3.xlsx")
    fake_fulcra.download_file.assert_not_called()


# --- the panel -------------------------------------------------------------------


async def test_the_panel_is_an_mcp_app_resource(client, fake_fulcra):
    [content] = await client.read_resource(ft.FILE_MANAGER_URI)

    assert content.mimeType == "text/html;profile=mcp-app"
    for method in ("ui/initialize", "resources/read", "ui/download-file", "upload_file_chunk"):
        assert method in content.text


async def test_tools_declare_the_panel_and_app_only_visibility(client, fake_fulcra):
    tools = {t.name: t for t in await client.list_tools()}

    assert tools["open_file_manager"].meta["ui"] == {"resourceUri": ft.FILE_MANAGER_URI}
    for name in ("start_file_upload", "upload_file_chunk"):
        # Listed, so hosts can let the panel call them, but hidden from the model.
        assert tools[name].meta["ui"]["visibility"] == ["app"]
    assert "ui" not in (tools["get_file_download_link"].meta or {})


async def test_open_file_manager_helps_clients_without_the_panel(call, fake_fulcra):
    fake_fulcra.list_files.return_value = {"folders": ["/reports/2026"], "files": [FILE]}

    text = await call("open_file_manager", {"path": "reports"})

    fake_fulcra.list_files.assert_called_once_with("/reports")
    assert "write_file" in text and "get_file_download_link" in text
    assert '"q3.xlsx"' in text


# --- uploads ---------------------------------------------------------------------


@pytest.fixture
def put_chunks(monkeypatch):
    """Stand in for the storage service: commits every chunk it's given."""
    sent = []

    def fake_put(url, data, start, total):
        sent.append((url, data, start, total))
        return start + len(data)

    monkeypatch.setattr(ft, "_put_chunk", fake_put)
    return sent


def _start(fake_fulcra, size):
    fake_fulcra.fulcra_api.return_value = json.dumps(
        {"url": "https://storage.example/upload?id=1", "file": dict(FILE, size=size)}
    ).encode()


async def _structured(client, name, args):
    result = await client.call_tool(name, args)
    return result.structured_content


async def test_an_upload_goes_through_in_chunks(client, fake_fulcra, put_chunks):
    size = ft.UPLOAD_GRANULE + 5
    _start(fake_fulcra, size)
    data = bytes(range(256)) * (size // 256) + bytes(size % 256)

    started = await _structured(
        client, "start_file_upload", {"path": "/reports/q3.xlsx", "size": size}
    )
    fake_fulcra.fulcra_api.assert_called_once_with(
        "/input/v1/file_upload",
        method="POST",
        data={
            "content_length": size,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "name": "q3.xlsx",
            "path": "/reports",
        },
    )
    first = await _structured(
        client,
        "upload_file_chunk",
        {
            "upload_id": started["upload_id"],
            "offset": 0,
            "data": base64.b64encode(data[: ft.UPLOAD_GRANULE]).decode(),
        },
    )
    assert (first["received"], first["done"]) == (ft.UPLOAD_GRANULE, False)

    last = await _structured(
        client,
        "upload_file_chunk",
        {
            "upload_id": started["upload_id"],
            "offset": ft.UPLOAD_GRANULE,
            "data": base64.b64encode(data[ft.UPLOAD_GRANULE :]).decode(),
        },
    )
    assert last["done"] and last["path"] == "/reports/q3.xlsx"
    assert last["resource_uri"] == "fulcra://files/reports/q3.xlsx"
    assert b"".join(chunk for _, chunk, _, _ in put_chunks) == data
    assert [(start, total) for _, _, start, total in put_chunks] == [
        (0, size),
        (ft.UPLOAD_GRANULE, size),
    ]


@pytest.mark.parametrize(
    "offset, chunk, message",
    [
        (0, b"x" * 1000, "multiple of 262144"),
        (5, b"x" * ft.UPLOAD_GRANULE, "Expected the chunk starting at byte 0"),
        (0, b"x" * (2 * ft.UPLOAD_GRANULE + 1), "past the file's size"),
    ],
)
async def test_bad_chunks_are_refused(client, fake_fulcra, put_chunks, offset, chunk, message):
    _start(fake_fulcra, 2 * ft.UPLOAD_GRANULE)
    started = await _structured(client, "start_file_upload", {"path": "/a.bin", "size": 2 * ft.UPLOAD_GRANULE})

    result = await client.call_tool(
        "upload_file_chunk",
        {"upload_id": started["upload_id"], "offset": offset, "data": base64.b64encode(chunk).decode()},
        raise_on_error=False,
    )

    assert result.is_error and message in result.content[0].text
    assert put_chunks == []


async def test_a_resent_chunk_is_harmless(client, fake_fulcra, put_chunks):
    _start(fake_fulcra, 2 * ft.UPLOAD_GRANULE)
    started = await _structured(client, "start_file_upload", {"path": "/a.bin", "size": 2 * ft.UPLOAD_GRANULE})
    chunk = {"upload_id": started["upload_id"], "offset": 0, "data": base64.b64encode(b"x" * ft.UPLOAD_GRANULE).decode()}

    await client.call_tool("upload_file_chunk", chunk)
    again = await _structured(client, "upload_file_chunk", chunk)

    assert again["received"] == ft.UPLOAD_GRANULE and len(put_chunks) == 1


async def test_resending_the_last_chunk_returns_the_same_result(client, fake_fulcra, put_chunks):
    _start(fake_fulcra, 3)
    started = await _structured(client, "start_file_upload", {"path": "/a.bin", "size": 3})
    last = {"upload_id": started["upload_id"], "offset": 0, "data": base64.b64encode(b"abc").decode()}

    first = await _structured(client, "upload_file_chunk", last)
    again = await _structured(client, "upload_file_chunk", last)

    assert first["done"] and again == first
    assert len(put_chunks) == 1  # stored once


async def test_resending_an_empty_files_only_chunk_returns_the_same_result(client, fake_fulcra, put_chunks):
    _start(fake_fulcra, 0)
    started = await _structured(client, "start_file_upload", {"path": "/empty.txt", "size": 0})
    only = {"upload_id": started["upload_id"], "offset": 0, "data": ""}

    first = await _structured(client, "upload_file_chunk", only)
    again = await _structured(client, "upload_file_chunk", only)

    assert first["done"] and again == first
    assert len(put_chunks) == 1


async def test_an_empty_file_uploads(client, fake_fulcra, put_chunks):
    _start(fake_fulcra, 0)
    started = await _structured(client, "start_file_upload", {"path": "/empty.txt", "size": 0})

    done = await _structured(client, "upload_file_chunk", {"upload_id": started["upload_id"], "offset": 0, "data": ""})

    assert done["done"] and put_chunks[0][1:] == (b"", 0, 0)


async def test_someone_elses_upload_is_unknown(client, fake_fulcra, put_chunks, monkeypatch):
    _start(fake_fulcra, 1)
    started = await _structured(client, "start_file_upload", {"path": "/a.bin", "size": 1})
    monkeypatch.setattr(ft, "current_grant_id", lambda: "another-login")

    result = await client.call_tool(
        "upload_file_chunk",
        {"upload_id": started["upload_id"], "offset": 0, "data": "eA=="},
        raise_on_error=False,
    )

    assert result.is_error and "No upload" in result.content[0].text


def test_put_chunk_reads_partial_progress(monkeypatch):
    import urllib.error

    def resume_incomplete(request):
        assert request.get_header("Content-range") == "bytes 0-3/10"
        raise urllib.error.HTTPError(request.full_url, 308, "Resume", {"Range": "bytes=0-3"}, None)

    monkeypatch.setattr(ft.urllib.request, "urlopen", resume_incomplete)
    assert ft._put_chunk("https://storage.example/u", b"abcd", 0, 10) == 4


# --- download links ----------------------------------------------------------------


async def test_a_local_server_saves_the_file_to_downloads(call, fake_fulcra, tmp_path, monkeypatch):
    monkeypatch.setattr(ft.Path, "home", lambda: tmp_path)
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Downloads" / "q3.xlsx").write_bytes(b"old")
    fake_fulcra.resolve_filepath.return_value = [FILE]
    _download_returns(fake_fulcra, b"spreadsheet")

    text = await call("get_file_download_link", {"path": "/reports/q3.xlsx"})

    saved = tmp_path / "Downloads" / "q3 (1).xlsx"
    assert saved.read_bytes() == b"spreadsheet"
    assert str(saved) in text


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(settings, "fulcra_environment", "hosted")
    monkeypatch.setattr(settings, "oidc_server_url", "https://mcp.example")
    monkeypatch.setattr(ft, "current_grant_id", lambda: "grant-1")


async def test_a_hosted_server_makes_a_short_lived_link(client, fake_fulcra, hosted):
    fake_fulcra.resolve_filepath.return_value = [FILE]

    link = await _structured(client, "get_file_download_link", {"path": "/reports/q3.xlsx"})

    assert link["url"].startswith("https://mcp.example/files/download/")
    token = link["url"].rsplit("/", 1)[1]
    target = ft.download_link_target(token)
    assert target["grant_id"] == "grant-1" and target["file_id"] == "f-1"
    # only a hash of the token is stored
    assert token not in "".join(p.name for p in settings.state_path.rglob("*"))


def test_the_download_route_streams_the_file(fake_fulcra, monkeypatch):
    import fulcra_mcp.main as main

    ft._save_record(
        "download_links",
        "tok",
        {"grant_id": "g", "file_id": "f-1", "fulcra_userid": None, "name": "Q3 résumé.xlsx", "expires_at": time.time() + 60},
    )
    monkeypatch.setattr(main.oauth_provider, "reload_grant", lambda grant_id: object())
    monkeypatch.setattr(main, "fulcra_for_grant", lambda grant_id, creds: fake_fulcra)
    upstream = io.BytesIO(b"spreadsheet")
    upstream.headers = {"Content-Length": "11"}
    fake_fulcra.download_file.return_value = upstream

    response = TestClient(main.app).get("/files/download/tok")

    assert response.status_code == 200 and response.content == b"spreadsheet"
    assert "attachment" in response.headers["content-disposition"]
    assert "filename*=UTF-8''Q3%20r%C3%A9sum%C3%A9.xlsx" in response.headers["content-disposition"]
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_an_expired_link_says_so(fake_fulcra):
    import fulcra_mcp.main as main

    ft._save_record("download_links", "old", {"grant_id": "g", "file_id": "f", "name": "a", "expires_at": time.time() - 1})

    response = TestClient(main.app).get("/files/download/old")

    assert response.status_code == 410 and "expired" in response.text
    assert not list((settings.state_path / "download_links").glob("*.json"))


# --- read_file and write_file --------------------------------------------------------


async def test_read_file_returns_a_spreadsheet_as_csv(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [FILE]
    _download_returns(fake_fulcra, _xlsx())

    text = await call("read_file", {"path": "/reports/q3.xlsx"})

    assert "(as CSV" in text
    assert "# Sheet: Totals\nregion,sales\nwest,12" in text
    assert '"say ""hi"", ok"' in text


class LimitedResponse(io.BytesIO):
    """A download that records how much was asked of it."""

    def __init__(self, data):
        super().__init__(data)
        self.asked = []

    def read(self, size=-1):
        self.asked.append(size)
        return super().read(size)


def _sparse_xlsx(far_cell: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "first"
    sheet[far_cell] = "last"
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


async def test_a_workbook_spanning_the_whole_grid_converts_within_bounds(call, fake_fulcra):
    data = _sparse_xlsx("XFD1048576")  # Excel's last cell
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, size=len(data))]
    _download_returns(fake_fulcra, data)

    started = time.monotonic()
    text = await call("read_file", {"path": "/reports/q3.xlsx", "max_bytes": 5000})

    assert time.monotonic() - started < 10
    assert len(text) < 5500
    assert text.count("\n") < 50  # empty rows and trailing cells are left out
    assert "only the first 200 columns" in text
    assert "stopped after" in text


def test_conversion_stops_at_the_text_limit():
    workbook = Workbook()
    for i in range(5000):
        workbook.active.append([f"row {i}", i])
    out = io.BytesIO()
    workbook.save(out)

    text = ft.spreadsheet_as_csv(out.getvalue(), 1000)

    assert "row 0,0" in text and "row 4999" not in text
    assert "stopped after the text limit" in text
    assert len(text) < 1100


async def test_a_large_spreadsheet_is_refused_before_downloading(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, size=ft.MAX_SPREADSHEET_FILE_BYTES + 1)]

    text = await call("read_file", {"path": "/reports/q3.xlsx"})

    assert "too large to convert" in text and "get_file_download_link" in text
    fake_fulcra.download_file.assert_not_called()


async def test_conversion_runs_off_the_event_loop(call, fake_fulcra, monkeypatch):
    import fulcra_mcp.tools as tools_module

    fake_fulcra.resolve_filepath.return_value = [FILE]
    _download_returns(fake_fulcra, _xlsx())
    ran = []
    real = tools_module.asyncio.to_thread

    async def recording(func, *args):
        ran.append(func.__name__)
        return await real(func, *args)

    monkeypatch.setattr(tools_module.asyncio, "to_thread", recording)
    await call("read_file", {"path": "/reports/q3.xlsx"})

    assert ran == ["spreadsheet_as_csv"]


async def test_text_is_read_only_as_far_as_max_bytes(call, fake_fulcra):
    response = LimitedResponse("é".encode() * 50_000)  # 100,000 bytes
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="a.txt", size=100_000)]
    fake_fulcra.download_file.return_value = response

    text = await call("read_file", {"path": "/a.txt", "max_bytes": 1001})

    assert response.asked == [1005]
    assert "truncated to the first 1001 bytes of 100000 bytes" in text
    # the character cut in half at the limit is dropped, not garbled
    assert text.endswith("é" * 500)


async def test_max_bytes_is_capped(call, fake_fulcra):
    response = LimitedResponse(b"x" * 10)
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="a.txt", size=10)]
    fake_fulcra.download_file.return_value = response

    await call("read_file", {"path": "/a.txt", "max_bytes": 10**12})

    assert response.asked == [ft.MAX_RESOURCE_BYTES + 4]


async def test_large_binary_with_include_binary_is_refused_before_downloading(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="a.bin", size=1_000_000)]

    text = await call("read_file", {"path": "/a.bin", "include_binary": True})

    assert "exceeding max_bytes" in text and "get_file_download_link" in text
    fake_fulcra.download_file.assert_not_called()


async def test_read_file_on_other_binaries_says_what_to_do(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [dict(FILE, name="photo.jpg")]
    _download_returns(fake_fulcra, b"\xff\xd8\xff\xe0")

    text = await call("read_file", {"path": "/photo.jpg"})

    assert "get_file_download_link" in text
    assert "fulcra://files/photo.jpg" in text
    assert "include_binary" in text


async def test_write_file_takes_base64_and_guesses_the_type(call, fake_fulcra):
    fake_fulcra.upload_file.return_value = {"file": FILE}

    await call(
        "write_file",
        {"path": "/reports/q3.xlsx", "content": base64.b64encode(b"\x00\xffxl").decode(), "encoding": "base64"},
    )

    fake_fulcra.upload_file.assert_called_once_with(
        b"\x00\xffxl",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        4,
        "/reports/q3.xlsx",
    )


async def test_write_file_guesses_text_types(call, fake_fulcra):
    fake_fulcra.upload_file.return_value = {"file": FILE}

    await call("write_file", {"path": "/state.json", "content": "{}"})

    fake_fulcra.upload_file.assert_called_once_with(b"{}", "application/json", 2, "/state.json")


async def test_write_file_refuses_bad_or_large_base64(call, fake_fulcra, monkeypatch):
    bad = await call("write_file", {"path": "/a.bin", "content": "not base64!", "encoding": "base64"})
    monkeypatch.setattr(ft, "MAX_WRITE_BASE64_BYTES", 2)
    large = await call("write_file", {"path": "/a.bin", "content": "AAAA", "encoding": "base64"})

    assert "isn't valid base64" in bad
    assert "start_file_upload" in large and "open_file_manager" in large
    fake_fulcra.upload_file.assert_not_called()
