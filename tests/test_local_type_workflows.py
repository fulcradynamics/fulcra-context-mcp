"""Opt-in end-to-end checks against fulcra-platform-local, never production.

FULCRA_LOCAL_AUDIT_USER=<local user UUID> \
FULCRA_LOCAL_AUDIT_PEER=<second local user UUID> \
uv run pytest tests/test_local_type_workflows.py -v

Creates disposable types/records and a temporary share. Archives the types,
deletes the share, and submits tombstones for the records in cleanup. Uses the
real SDK above a localhost-only transport with the dev services' identity
headers. No credentials are read and no login is needed.
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jsonschema
import pytest
from fulcra_api.core import FulcraAPI

import fulcra_mcp.tools as tools_module

pytestmark = pytest.mark.skipif(
    not os.environ.get("FULCRA_LOCAL_AUDIT_USER"),
    reason="requires explicitly selected local dev accounts",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class LocalFulcra(FulcraAPI):
    def __init__(self, user_id):
        super().__init__(oidc_audience="http://localhost:8008/")
        self.user_id = str(UUID(user_id))
        self.opener = urllib.request.build_opener(NoRedirect())

    def get_fulcra_userid(self):
        return self.user_id

    def fulcra_api(
        self, url_path, method="GET", query=None, data=None,
        return_http_response=False, content_type="application/json",
        authenticated=True,
    ):
        path = "/" + urllib.parse.urlparse(url_path).path.lstrip("/")
        port = {"data": 8083, "input": 8086, "user": 8081, "ingest": 8000}[
            path.split("/")[1]
        ]
        url = f"http://localhost:{port}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        payload = None
        if data is not None:
            if content_type == "application/x-jsonl":
                payload = "\n".join(json.dumps(r) for r in data) + "\n"
            else:
                payload = json.dumps(data)
            payload = payload.encode()
        headers = {
            "X-FULCRA-USERID": self.user_id,
            "X-FULCRA-SCOPE": "openid email profile",
            "Content-Type": content_type,
        }
        request = urllib.request.Request(url, payload, headers, method=method)
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            if error.code != 303:
                raise
            # Re-route redirects to the internal service, retaining dev headers.
            return self.fulcra_api(error.headers["Location"])
        if return_http_response:
            return response
        with response:
            return response.read()


def payload(text):
    return json.loads(text[text.index("{"):])


@pytest.fixture
def local_fulcra(monkeypatch):
    source = LocalFulcra(os.environ["FULCRA_LOCAL_AUDIT_USER"])
    monkeypatch.setattr(tools_module, "get_fulcra_object", lambda: source)
    return source


async def wait_for_record(call, type_id, start, end, matches, **kwargs):
    deadline = time.monotonic() + 30
    while True:
        text = await call("get_records", {
            "data_type": type_id, "start_time": start, "end_time": end, **kwargs,
        })
        rows = json.loads(text[text.index("["):])
        found = [row for row in rows if matches(row)]
        if found:
            return found[0]
        if time.monotonic() >= deadline:
            pytest.fail(f"accepted record did not become visible for {type_id}: {text}")
        await asyncio.sleep(1)


# A note must be explicitly declared for v1, unlike annotations.
NOTE = {"properties": {"note": {"type": "string"}}}
CASES = [
    ("moment", {}, None, False),
    ("duration", {}, None, True),
    pytest.param("boolean", {"default_value": "false", "metric_kind": "discrete"}, "false", False,
                 marks=pytest.mark.xfail(strict=True, reason="pre-existing BooleanAnnotation schema expects a number")),
    ("numeric", {"unit": "mg", "metric_kind": "cumulative"}, "4.5", False),
    ("scale", {"scale_labels": ["a", "b", "c", "d", "e"]}, "3", False),
    ("event", {"fields": NOTE}, None, False),
    ("event", {"fields": NOTE}, None, True),
    ("metric", {"fields": NOTE, "scale": {"min": 0, "max": 1},
                "value_map": {"0": "False", "1": "True"}}, "0", False),
    ("metric", {"fields": NOTE, "unit": "mg", "metric_kind": "cumulative"}, "4.5", False),
    ("metric", {"fields": NOTE, "scale": {"min": 1, "max": 5},
                "value_map": {str(i): str(i) for i in range(1, 6)}}, "3", False),
]


@pytest.mark.parametrize("base,options,value,duration", CASES)
async def test_create_record_read_archive_restore(call, local_fulcra, base, options, value, duration):
    marker = f"mcp-type-audit-{uuid4()}"
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    created = await call("create_data_type", {
        "base_type": base, "name": marker, "description": "Disposable MCP compatibility audit",
        **options,
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    row = None
    tag = None
    tag_name = f"audit-{uuid4().hex[:16]}"
    try:
        catalog = payload(await call("get_data_catalog", {"data_type": type_id}))
        assert any(e["id"] == type_id for group in catalog.values() for e in group)
        tag = local_fulcra.create_tag(tag_name)
        args = {"data_type": type_id, "note": marker, "start_time": start, "tags": [tag_name]}
        if duration:
            args["end_time"] = now.isoformat()
        if value is not None:
            args["value"] = value
        written = await call("record_data", args)
        assert written.startswith("Recorded 1 "), written
        row = await wait_for_record(call, type_id, start, end, lambda r: r.get("note") == marker)
        assert row["note"] == marker
        assert tag["id"] in row["tags"]
        if value is not None:
            assert row["value"] == json.loads(value)
        # A duration must also be visible in a window strictly inside it.
        if duration:
            await wait_for_record(call, type_id,
                                  (now - timedelta(minutes=30)).isoformat(),
                                  (now - timedelta(minutes=20)).isoformat(),
                                  lambda r: r.get("note") == marker)
        assert (await call("archive_data_type", {"data_type": type_id})).startswith("Archived")
        assert (await call("restore_data_type", {"data_type": type_id})).startswith("Restored")
        await wait_for_record(call, type_id, start, end, lambda r: r.get("note") == marker)
    finally:
        if row:
            local_fulcra.record_data_type("DeletedRecord", [{
                "data_type": type_id.split("/")[0], "record_id": row["id"],
            }], "v1" if base in ("event", "metric") else "v1alpha1")
        await call("archive_data_type", {"data_type": type_id})
        if tag:
            local_fulcra.delete_tag(tag["id"])


async def test_v1_nested_workspace_and_peer_read(call, local_fulcra):
    peer_id = os.environ.get("FULCRA_LOCAL_AUDIT_PEER")
    if not peer_id:
        pytest.skip("requires FULCRA_LOCAL_AUDIT_PEER")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).isoformat()
    end = (now + timedelta(minutes=5)).isoformat()
    envelope = {"message_id": str(uuid4()), "body": "Review message", "recipients": ["peer"]}
    fields = {"properties": {"coord": {
        "type": "object", "required": ["message_id", "body", "recipients"],
        "properties": {"message_id": {"type": "string"}, "body": {"type": "string"},
                       "recipients": {"type": "array", "items": {"type": "string"}}},
    }}, "required": ["coord"]}
    created = await call("create_data_type", {
        "base_type": "event", "name": f"mcp-message-audit-{uuid4()}",
        "description": "Disposable nested message audit", "fields": fields,
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    share_id = None
    row = None
    try:
        written = await call("record_data", {
            "data_type": type_id, "start_time": now.isoformat(), "fields": {"coord": envelope},
        })
        assert written.startswith("Recorded 1 "), written
        row = await wait_for_record(call, type_id, start, end, lambda r: r.get("coord") == envelope)
        shared = payload(await call("create_share", {
            "name": "Disposable MCP audit share", "data_types": [type_id], "with_user_ids": [peer_id],
        }))
        share_id = shared["datashare_id"]
        peer = LocalFulcra(peer_id)
        tools_module.get_fulcra_object = lambda: peer
        received = await wait_for_record(call, type_id, start, end,
                                         lambda r: r.get("coord") == envelope,
                                         fulcra_userid=local_fulcra.user_id)
        assert received["coord"] == envelope
    finally:
        tools_module.get_fulcra_object = lambda: local_fulcra
        if share_id:
            await call("delete_share", {"share_id": share_id})
        if row:
            local_fulcra.record_data_type("DeletedRecord", [{
                "data_type": "Event", "record_id": row["id"],
            }], "v1")
        await call("archive_data_type", {"data_type": type_id})


async def test_nested_schema_constraints_survive_catalog_roundtrip(call, local_fulcra):
    fields = {"properties": {"coord": {"type": "object", "required": ["body"],
                                        "properties": {"body": {"type": "string"}}}},
              "required": ["coord"]}
    created = await call("create_data_type", {
        "base_type": "event", "name": f"mcp-schema-audit-{uuid4()}",
        "description": "Disposable schema audit", "fields": fields,
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    try:
        # The ETL validates the original schema, so accepting this locally can
        # yield an upload ID followed by a silently dropped record.
        errors = local_fulcra.validate_records(type_id, [{"coord": {"body": 42}}], "v1")
        assert errors, "invalid nested message passed SDK validation"
    finally:
        await call("archive_data_type", {"data_type": type_id})


async def test_peer_can_discover_shared_v1_fields(call, local_fulcra):
    peer_id = os.environ.get("FULCRA_LOCAL_AUDIT_PEER")
    if not peer_id:
        pytest.skip("requires FULCRA_LOCAL_AUDIT_PEER")
    created = await call("create_data_type", {
        "base_type": "event", "name": f"mcp-discovery-audit-{uuid4()}",
        "description": "Disposable shared schema audit", "fields": NOTE,
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    share_id = None
    try:
        shared = payload(await call("create_share", {
            "name": "Disposable discovery audit", "data_types": [type_id], "with_user_ids": [peer_id],
        }))
        share_id = shared["datashare_id"]
        peer = LocalFulcra(peer_id)
        tools_module.get_fulcra_object = lambda: peer
        text = await call("get_data_catalog", {
            "data_type": type_id, "fulcra_userid": local_fulcra.user_id,
        })
        assert text.startswith("Available data types"), text
        entries = [entry for group in payload(text).values() for entry in group]
        assert entries[0]["fields"] == {"note": "string"}
        assert entries[0]["recordable"] is False
        assert entries[0]["fulcra_userid"] == local_fulcra.user_id
    finally:
        tools_module.get_fulcra_object = lambda: local_fulcra
        if share_id:
            await call("delete_share", {"share_id": share_id})
        await call("archive_data_type", {"data_type": type_id})


@pytest.mark.xfail(strict=True, raises=jsonschema.ValidationError,
                   reason="MCP catalog discards nullable custom field semantics")
@pytest.mark.parametrize("field", [
    {"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}]},
    {"type": ["string", "null"], "minLength": 1},
])
async def test_nullable_schema_catalog_matches_sdk_validation(call, local_fulcra, field):
    created = await call("create_data_type", {
        "base_type": "event", "name": f"mcp-nullability-audit-{uuid4()}",
        "description": "Disposable schema fidelity audit",
        "fields": {"properties": {"state": field}, "required": ["state"]},
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    try:
        assert not local_fulcra.validate_records(type_id, [{"state": None}], "v1")
        catalog = payload(await call("get_data_catalog", {"data_type": type_id}))
        [entry] = [e for group in catalog.values() for e in group]
        assert entry["required_fields"] == ["state"]
        jsonschema.validate(None, entry["fields"]["state"])
    finally:
        await call("archive_data_type", {"data_type": type_id})


async def wait_until(check, what, seconds=60):
    deadline = time.monotonic() + seconds
    while not await check():
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(1)


async def test_connection_channel_lifecycle(call, local_fulcra):
    """The tools a private agent-to-agent channel needs (PLAT-668): a record id
    from record_data, resending it, delete_records, an ended share reported as
    such, and declining someone's share with leave_share."""
    peer_id = os.environ.get("FULCRA_LOCAL_AUDIT_PEER")
    if not peer_id:
        pytest.skip("requires FULCRA_LOCAL_AUDIT_PEER")
    peer = LocalFulcra(peer_id)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).isoformat()
    end = (now + timedelta(minutes=5)).isoformat()
    fields = {"properties": {"sender": {"type": "string"}, "body": {"type": "string"}},
              "required": ["sender", "body"]}
    created = await call("create_data_type", {
        "base_type": "event", "name": f"mcp-channel-audit-{uuid4()}",
        "description": "Disposable connection channel audit", "fields": fields,
    })
    assert created.startswith("Created data type "), created
    type_id = created.split(": ", 1)[0].removeprefix("Created data type ")
    peer_type_id = None
    share_id = peer_share_id = None
    record_id = str(uuid4())
    message = {"sender": "audit-agent", "body": f"hello {record_id}"}
    try:
        # The id comes back from record_data, and a resend with it is one record.
        for _ in range(2):
            written = await call("record_data", {
                "data_type": type_id, "fields": message, "record_id": record_id,
            })
            assert f"with id {record_id}" in written, written
        shared = payload(await call("create_share", {
            "name": "Disposable channel audit", "data_types": [type_id], "with_user_ids": [peer_id],
        }))
        share_id = shared["datashare_id"]

        async def peer_rows():
            tools_module.get_fulcra_object = lambda: peer
            try:
                text = await call("get_records", {
                    "data_type": type_id, "start_time": start, "end_time": end,
                    "fulcra_userid": local_fulcra.user_id,
                })
            finally:
                tools_module.get_fulcra_object = lambda: local_fulcra
            return text, json.loads(text[text.index("["):]) if "[" in text else None

        async def peer_sees_it():
            _, rows = await peer_rows()
            return rows is not None and any(r["id"] == record_id for r in rows)

        await wait_until(peer_sees_it, "the peer to read the message")
        _, rows = await peer_rows()
        assert [r["id"] for r in rows].count(record_id) == 1

        # delete_records takes it back, for the peer too.
        deleted = await call("delete_records", {"data_type": type_id, "record_ids": [record_id]})
        assert deleted.startswith("Deleting 1 record from"), deleted

        async def gone():
            return not await peer_sees_it()

        await wait_until(gone, "the deleted message to disappear for the peer")

        # Once the share is deleted, the peer is told the data isn't shared,
        # not that the type doesn't exist.
        await call("delete_share", {"share_id": share_id})
        share_id = None
        text, _ = await peer_rows()
        assert text.startswith(f"User {local_fulcra.user_id} "), text
        assert "No data type found" not in text

        # The peer shares a channel of its own; this user declines it.
        tools_module.get_fulcra_object = lambda: peer
        peer_created = await call("create_data_type", {
            "base_type": "event", "name": f"mcp-channel-audit-peer-{uuid4()}",
            "description": "Disposable connection request audit", "fields": fields,
        })
        peer_type_id = peer_created.split(": ", 1)[0].removeprefix("Created data type ")
        peer_share_id = payload(await call("create_share", {
            "name": "Disposable connection request", "data_types": [peer_type_id],
            "with_user_ids": [local_fulcra.user_id],
        }))["datashare_id"]
        tools_module.get_fulcra_object = lambda: local_fulcra
        incoming = payload(await call("list_shares", {"direction": "incoming"}))["incoming"]
        [grant] = [g for g in incoming if g.get("datashare_id") == peer_share_id]
        left = await call("leave_share", {"grant_id": grant["grant_id"]})
        assert "no longer has access" in left, left
        incoming = payload(await call("list_shares", {"direction": "incoming"}))["incoming"]
        assert not [g for g in incoming if g.get("datashare_id") == peer_share_id]
    finally:
        tools_module.get_fulcra_object = lambda: local_fulcra
        if share_id:
            await call("delete_share", {"share_id": share_id})
        if peer_type_id:
            tools_module.get_fulcra_object = lambda: peer
            if peer_share_id:
                await call("delete_share", {"share_id": peer_share_id})
            await call("archive_data_type", {"data_type": peer_type_id})
            tools_module.get_fulcra_object = lambda: local_fulcra
        await call("archive_data_type", {"data_type": type_id})
