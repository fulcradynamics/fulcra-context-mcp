"""Exercise browsing through real SDK metadata queries, not SDK method mocks."""

import json
import urllib.error

import pytest
from fulcra_api.core import FulcraAPI

from fulcra_mcp import tools

OWNER = "00000000-0000-4000-8000-000000000002"


@pytest.mark.parametrize("tool", ["open_file_manager", "list_files"])
async def test_empty_owned_root_remains_browsable(call, monkeypatch, tool):
    sdk = FulcraAPI()
    queries = []

    def backend(endpoint, query):
        assert endpoint == "/input/v1/file_upload"
        queries.append(query)
        return json.dumps({"folders": [], "files": []})

    monkeypatch.setattr(sdk, "fulcra_api", backend)
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: sdk)
    text = await call(tool, {"path": "/"})
    assert '"folders": [], "files": []' in text
    if tool == "open_file_manager":
        from fulcra_mcp.file_transfer import WITHOUT_THE_PANEL

        assert "Showing the Fulcra file manager at /." in text
        assert "Files the user uploads" in text
        assert WITHOUT_THE_PANEL in text
    assert queries == [{"path": "/", "state": "uploaded"}]


@pytest.mark.parametrize("tool", ["open_file_manager", "list_files"])
@pytest.mark.parametrize("name", ["report.txt", "README"])
@pytest.mark.parametrize("owner", [OWNER, None])
async def test_exact_file_metadata_query(call, monkeypatch, tool, name, owner):
    sdk = FulcraAPI()
    queries = []

    def backend(endpoint, query):
        assert endpoint == "/input/v1/file_upload"
        queries.append(query)
        assert query.get("fulcra_userid") == owner
        assert query["state"] == "uploaded"
        if query == {"path": "/shared", "name": name, "state": "uploaded", **({"fulcra_userid": owner} if owner else {})}:
            return json.dumps({"files": [{"name": name, "path": "/shared"}]})
        assert query["path"] == f"/shared/{name}" and "name" not in query
        if owner:
            raise urllib.error.HTTPError(endpoint, 403, "Forbidden", None, None)
        return json.dumps({"folders": [], "files": []})

    monkeypatch.setattr(sdk, "fulcra_api", backend)
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: sdk)
    text = await call(tool, {"path": f"/shared/{name}", **({"fulcra_userid": owner} if owner else {})})
    assert f'"name": "{name}"' in text
    assert len(queries) == 2
    if owner and tool == "open_file_manager":
        assert owner in text and "read-only" in text


@pytest.mark.parametrize("tool", ["open_file_manager", "list_files"])
@pytest.mark.parametrize("code", [403, 401, 500])
async def test_denied_browsing_never_changes_owner_or_lists_parent(call, monkeypatch, tool, code):
    sdk = FulcraAPI()
    queries = []

    def backend(endpoint, query):
        queries.append(query)
        assert endpoint == "/input/v1/file_upload"
        assert query.get("fulcra_userid") == OWNER
        assert query["path"] == "/shared/README" or (
            code == 403 and query["path"] == "/shared" and query["name"] == "README"
        )
        raise urllib.error.HTTPError(endpoint, code, "Denied", None, None)

    monkeypatch.setattr(sdk, "fulcra_api", backend)
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: sdk)
    text = await call(tool, {"path": "/shared/README", "fulcra_userid": OWNER})
    assert "Showing" not in text
    assert len(queries) == (2 if code == 403 else 1)
    if code == 403:
        assert "has not shared" in text


@pytest.mark.parametrize("tool", ["open_file_manager", "list_files"])
async def test_dotted_directory_stays_a_directory(call, monkeypatch, tool):
    sdk = FulcraAPI()
    queries = []

    def backend(endpoint, query):
        queries.append(query)
        assert query == {"path": "/shared/reports.v1", "state": "uploaded", "fulcra_userid": OWNER}
        return json.dumps({"folders": ["/shared/reports.v1/child"], "files": []})

    monkeypatch.setattr(sdk, "fulcra_api", backend)
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: sdk)
    text = await call(tool, {"path": "/shared/reports.v1", "fulcra_userid": OWNER})
    assert '"/shared/reports.v1/child"' in text
    assert len(queries) == 1
