# Channel matching and durable decisions

Prefixes such as `connect-our-agents channel` and protocol-named shares are discovery hints, not eligibility requirements. Selected channels require exact backend ownership, an active compatible Event schema, current access and the intended outgoing audience. Missing metadata does not invalidate a usable selected channel. Explicit user/agent matching need not use invitation evidence.

## Public description marker

Store one `[agent_connection: <JSON object>]` on the OWN outbox description:

```text
[agent_connection: {"version":1,"peers":[{"fulcra_userid":"00000000-0000-0000-0000-000000000002","data_type":"Event/00000000-0000-0000-0000-000000000020"}]}]
Project notes
[mesh_identifier: "Alex"]
```

Example identities are synthetic. `peers` is an optional array of incoming owner/channel pairs, allowing multiple peers and multiple channels per peer. UUIDs are exact lowercase hex 8-4-4-4-12; channels are `Event/<UUID>`. The containing outbox owner and ID come from the catalog. These pairs record resolved decisions, not membership or authorization. Current narrow outgoing grants still define the expected audience; broad shares neither veto nor widen it.

Both inviter and invitee save their own pair when the return channel is available and resolved. Neither side needs symmetrical metadata or permission to edit a peer's channel. Model workflows use `update_data_type` with `expected_description`, require `verified=true` and independently reread the exact channel. No additional model tool is needed. Match, send, invitation and sharing consent remain distinct.

Find the marker by token even in whitespace-folded catalog descriptions, JSON-decode its object, then require `]`. Replace only that span, or prepend it and a newline when absent. Preserve unrelated text, unknown metadata keys, labels (the final `mesh_identifier` suffix), preferences, setup-session and conversion metadata. Malformed metadata stops editing that marker, not an independently authorized send. The stale-description guard and process lock are not cross-worker compare-and-swap.

## Invitations

`invitation` is optional within this marker. There is no separate invitation store:

```json
{"version":1,"invitation":{"code":"00000000000000000000000000000001","prefix":"handshake","state":"prepared"}}
```

An individual invitation uses a secure unique `[0-9a-f]{32}` code, `prefix:"handshake"`, and `state` of `prepared`, `consumed`, or `completed`. Consumed/completed entries carry `peer_userid` and `incoming_data_type`. Completion records that pair in `peers`. Persist and verify consumption before sharing; uncertainty never rearms a consumed invitation. Explicit matches do not reset invitation state.

Open invitations use `prefix:"open_invitation"`, remain `prepared`, and keep `responses` keyed by responder user ID. A response stores `incoming_data_type`, display `identifier`, and state `creating`, `prepared`, `consumed`, or `completed`; all except `creating` require a distinct response outbox `data_type`. The individual response outbox records its own pair before the response is completed. Do not copy template invitation metadata or the standing inviter name to response outboxes. Open templates never appear as contacts and cannot be used for sends, reply targets or response evidence.

The app's automatic matcher still requires an unambiguous earliest first-message code for preauthorized return-sharing, preserving consumption and uncertainty semantics. That is one way to resolve a pair, not a requirement for all matching. The plugin handles invitee persistence and explicit matching through the public metadata tool. UI discovery consumes own saved pairs without requiring a peer marker; it always rechecks access and schema. Released legacy mesh conversion/history remains supported.
