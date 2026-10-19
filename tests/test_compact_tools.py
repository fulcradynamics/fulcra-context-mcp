"""The tool list and results leave out what costs context without telling a
model anything: duplicate structured copies of text results, and nullable
anyOf wrappers on optional parameters."""

import json

import pytest

from fulcra_mcp.compact_tools import compact_schema

START = "2026-08-01T00:00:00-07:00"


@pytest.mark.parametrize(
    "schema, expected",
    [
        (
            {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
            {"type": "string"},
        ),
        (
            {
                "anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}],
                "default": None,
                "description": "When",
            },
            {"type": "string", "format": "date-time", "description": "When"},
        ),
        (
            {"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}]},
            {"items": {"type": "string"}, "type": "array"},
        ),
        # Defaults other than null, and unions of two real types, are kept.
        ({"type": "integer", "default": 900}, {"type": "integer", "default": 900}),
        (
            {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        ),
        (
            {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
            {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
        ),
        # Nested properties are compacted too.
        (
            {
                "type": "object",
                "properties": {"a": {"anyOf": [{"type": "number"}, {"type": "null"}]}},
            },
            {"type": "object", "properties": {"a": {"type": "number"}}},
        ),
    ],
    ids=["plain", "keeps-description", "array", "real-default", "two-types", "three-types", "nested"],
)
def test_compact_schema(schema, expected):
    assert compact_schema(schema) == expected


async def test_listed_tools_carry_no_nullable_wrappers(client):
    for tool in await client.list_tools():
        listed = json.dumps(tool.inputSchema)
        assert '{"type": "null"}' not in listed, tool.name
        assert '"default": null' not in listed, tool.name


async def test_only_object_results_keep_an_output_schema(client):
    tools = {t.name: t for t in await client.list_tools()}
    assert tools["get_user_info"].outputSchema is None
    assert tools["start_file_upload"].outputSchema is not None
    assert not [
        name
        for name, t in tools.items()
        if t.outputSchema and t.outputSchema.get("x-fastmcp-wrap-result")
    ]


async def test_text_results_are_sent_once(client, fake_fulcra):
    fake_fulcra.get_user_info.return_value = {"userid": "u1"}
    result = await client.call_tool_mcp("get_user_info", {})
    assert result.structuredContent is None
    assert result.content[0].text.startswith("User information: ")


async def test_an_explicit_null_is_still_accepted(call, fake_fulcra):
    fake_fulcra.location_at_time.return_value = []
    await call("get_location", {"time": START, "fulcra_userid": None})
    assert fake_fulcra.location_at_time.call_args.kwargs["fulcra_userid"] is None
