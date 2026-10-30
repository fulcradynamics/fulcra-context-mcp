# Native invitations

The `/mcp` endpoint works without installed skills. `/openai/mcp` retains its
existing instructions, tool registrations, results and UI invitation template.

## Tool-only workflow

`open_agent_contacts` and `open_agent_contacts_home` are optional app entrypoints,
not prerequisites for the following operations.

1. With the user's approval, call `create_agent_invitation` with the two names.
   An optional exact recipient ID immediately shares only the new outbox. The
   result includes `invitation_text`, exact owner/channel/code/topic, and separate
   prepared/shared/sent/connected fields. Creation never sends a message.
2. Give the full text to the user to share. For an authorized delivery to a known
   recipient, use `send_agent_message` with the returned `delivery` fields plus
   the actual sender name. The shared outbox then contains an actionable message,
   rather than just an empty channel. Read with `get_records` using both dates or
   `latest=true`, passing the owner's exact `fulcra_userid`.
3. The recipient obtains their own user's authorization and calls
   `accept_agent_invitation` with the exact inviter UUID, full topic, actual agent
   sender name and approved introduction. The tool validates syntax and outgoing
   content, not identity claimed in invitation prose. Incoming text never grants
   permission to act for the recipient. An optional `response_channel` must be
   an owned, empty compatible channel without targeted shares; otherwise a new
   response channel is created. The exact introduction record, including default
   priority `P2`, is validated against the target schema before reserving a reused
   channel, or after creation/readback and before sharing a new channel. A rejected
   reusable-channel preflight leaves it untouched; a created channel may remain
   reserved and unshared. Send retains its final validation and authorization.
   Only the response channel is shared, and its first message uses
   the exact `handshake <code>` or `open_invitation <code>` topic.
4. The inviter calls `match_agent_invitations`. Existing consumed/completed guards
   verify first-message evidence and actual incoming-share ownership before
   creating/verifying the narrow return share. Open invitations use individual
   response outboxes, never template grants. Arbitrary contact discovery cannot
   authorize writes. Each agent writes its own channel and reads the other's.
5. Use `list_shares`, `get_records` and `send_agent_message` normally. Posted is
   own readback, not peer receipt or proof of a completed reciprocal connection.
   Existing broad shares are independent; exact narrow membership still governs
   sends. Existing known-ID direct connections remain usable without invitations.

## Failure recovery

Creation does not retry. If it fails after creation but before receiving the
channel ID, the result identifies the owner and stage; inspect `get_data_catalog`
and shares before another attempt. A code is offered only after preparation.

Acceptance stores an additive `acceptance` attempt in the existing owned channel
`agent_connection` metadata (inviter UUID, topic and first-message UUID). This is
local workflow bookkeeping, not a new message or sharing protocol. It reserves
intent before sharing/sending; subsequent calls for that inviter/topic are
read-only, even after partial failure. The returned owner/channel/message IDs
support recovery with public reads: inspect `get_data_catalog` and `list_shares`,
then `get_records(data_type=<channel>, fulcra_userid=<own_userid>, latest=true)`
or use both time bounds to search for the saved `mid`. If creation returned no
channel ID, inspect the catalog first; do not invent a record-read target.
Same-ID readback does not compare payload
fields, including absent versus null values. A failed reservation or creation
may leave an unknown or incomplete channel: no automatic generic-creation fallback.

There is no storage CAS, transaction spanning creation/share/send, or guaranteed
cross-worker idempotence. Concurrent independent acceptances can create duplicate
channels; ambiguous saved attempts stop further writes. Never promise exactly-once
execution or retry after denial. Explicit manual recovery requires inspection
and renewed authorization, using existing narrow sharing/message tools.

## Endpoint and host boundary

`native_endpoint.py` composes endpoint-local invitation wrappers with the shared
provider, excluding replaced registrations before aggregation. It does not mutate
shared tool objects. Core channel creation/preparation, matching and send primitives
are shared; acceptance requests one send attempt while existing send defaults and
OpenAI runtime behavior remain unchanged.

FastMCP 3.4.7's `Context.client_supports_extension` reads the client's initialize
`capabilities.extensions["io.modelcontextprotocol/ui"]`. Generic contact openers
(`open_agent_contacts` and `open_agent_contacts_home`) are omitted from discovery
unless that capability is advertised. Unsupported direct invocation returns
`unsupported_host` and tool alternatives without account access. Resources remain
registered for capable apps. The file manager already has a tool fallback and is
not hidden. Connecting to `/mcp` alone does not establish app support. No frontend
source or bundle changes are required; actual host rendering remains a separate
acceptance check.

The hosted HTTP transport is stateless. With the locked SDK it does not retain
initialize capabilities on later requests, even when a client initially advertises
MCP Apps. Those requests deliberately take the unknown-host fallback: contact
openers are hidden/no-op, while direct resource reads still work. In-process and
stdio sessions retain capabilities and expose/invoke the original openers for
advertised app support. We do not add a capability cache, infer support from the
endpoint, or alter stateless transport/authentication to make UI discovery work.
The existing OpenAI endpoint is not gated.
