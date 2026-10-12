"""send_agent_message (PLAT-696): sending a connect-agents-with-anyone message.

The checks themselves live in fulcra-api's `connections` module, which has its
own tests; these cover the tool's wiring."""

import json

from conftest import FAKE_USER_ID, http_error

PARTNER = "11111111-2222-4333-8444-555555555555"
CHANNEL = "Event/df10403a-2115-4254-9e49-e48ca0af6f5d"
THEIR_CHANNEL = "Event/7b0c5a51-3e6b-4f6e-9a7e-2f1d0f0c9a11"
THEIR_MESSAGE = "8d3b1c2e-1111-4a5b-9c6d-7e8f9a0b1c2d"
THEIR_ACK = "8d3b1c2e-2222-4a5b-9c6d-7e8f9a0b1c2d"


def _connected(fake_fulcra):
    fake_fulcra.get_datashares.return_value = [
        {
            "datashare_name": "connect-agents-with-anyone: Me with Pat",
            "fulcra_data_types": [CHANNEL],
            "permissions": [{"allowed_fulcra_userid": PARTNER}],
        }
    ]
    fake_fulcra.get_shared_datasets.return_value = [
        {"grant_type": "self", "sharing_fulcra_userid": FAKE_USER_ID},
        {
            "grant_type": "user",
            "datashare_name": "connect-agents-with-anyone: Pat with Me",
            "sharing_fulcra_userid": PARTNER,
            "fulcra_data_types": [THEIR_CHANNEL],
        },
    ]
    fake_fulcra.fulcra_v1_records.return_value = "\n".join(
        json.dumps(r)
        for r in [
            {"id": THEIR_MESSAGE, "kind": "message", "topic": "dinner", "body": "7?"},
            {"id": THEIR_ACK, "kind": "ack", "in_reply_to": THEIR_MESSAGE, "body": "ok"},
        ]
    )
    fake_fulcra.validate_records.return_value = []
    fake_fulcra.record_data_type.return_value = {"upload_id": "up-1"}


async def test_sends_on_your_channel_and_reports_the_id(call, fake_fulcra):
    _connected(fake_fulcra)

    text = await call(
        "send_agent_message",
        {"connection": PARTNER, "sender": "alice-claude", "body": 'It\'s "7pm"\nok'},
    )

    (target, [record], version), _ = fake_fulcra.record_data_type.call_args
    assert (target, version) == (CHANNEL, "v1")
    assert record["body"] == 'It\'s "7pm"\nok'
    assert record["sources"] == ["com.fulcradynamics.mcp"]
    assert text.startswith(f"Sent message {record['id']} on {CHANNEL}")
    assert "sources" not in text


async def test_a_reply_reuses_the_topic(call, fake_fulcra):
    _connected(fake_fulcra)

    text = await call(
        "send_agent_message",
        {"connection": CHANNEL, "sender": "a", "body": "Yes", "reply_to": THEIR_MESSAGE},
    )

    (_, [record], _), _ = fake_fulcra.record_data_type.call_args
    assert (record["kind"], record["in_reply_to"], record["topic"]) == (
        "reply",
        THEIR_MESSAGE,
        "dinner",
    )
    assert text.startswith("Sent reply")


async def test_a_refusal_is_explained_and_sends_nothing(call, fake_fulcra):
    _connected(fake_fulcra)

    text = await call(
        "send_agent_message",
        {"connection": PARTNER, "sender": "a", "body": "x", "reply_to": THEIR_ACK},
    )

    assert text.startswith("Not sent:") and "Acks aren't answered" in text
    fake_fulcra.record_data_type.assert_not_called()


async def test_a_bad_priority_is_refused_by_the_schema(client, fake_fulcra):
    _connected(fake_fulcra)

    result = await client.call_tool(
        "send_agent_message",
        {"connection": PARTNER, "sender": "a", "body": "x", "priority": "urgent"},
        raise_on_error=False,
    )

    assert result.is_error
    fake_fulcra.record_data_type.assert_not_called()


async def test_an_api_error_is_friendly(call, fake_fulcra):
    _connected(fake_fulcra)
    fake_fulcra.get_datashares.side_effect = http_error(500, b"boom")

    text = await call(
        "send_agent_message", {"connection": PARTNER, "sender": "a", "body": "x"}
    )

    assert "unexpected error (HTTP 500)" in text
