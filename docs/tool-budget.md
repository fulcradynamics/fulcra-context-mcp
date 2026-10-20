# Agent-plugin tool budget

Run from a checkout with locked dependencies:

```sh
FULCRA_ENVIRONMENT=prod uv run python scripts/measure_tools.py --codex --json
FULCRA_ENVIRONMENT=prod uv run python scripts/measure_tools.py --codex --deferred
```

`--namespace` must match the configured MCP server key (default: `fulcra`).
`--inventory snapshot.json` measures saved `{revision, instructions, tools}` MCP
metadata instead of importing the checkout. The optional positional checkout
path lets the current measurement script import another source revision. Default
mode without `--codex` retains the older character/token estimate; it is **not**
the agent-plugin budget. Codex mode defaults to `prod` even when the shell has
`FULCRA_ENVIRONMENT=stdio`; use `--environment stdio` for intentional local-only
measurement. JSON labels the environment, excluded app/local-only tools,
truncation and remaining shared bytes.

## Method and limitations

The implementation reference is public Codex
[`221e4e7c05386d06aa7b91da2a9b04f7f2bd921f`](https://github.com/openai/codex/tree/221e4e7c05386d06aa7b91da2a9b04f7f2bd921f),
not a guarantee about any deployed ChatGPT host. Source paths below are under
`codex-rs/`:

- `codex-mcp/src/rmcp_client.rs`: ordinary MCP server instructions become the
  namespace description; configured server/tool names become callable names.
- `tools/src/mcp_tool.rs`, `tools/src/json_schema.rs` and
  `tools/src/json_schema/{types,compaction}.rs`: truncate tool descriptions at a
  UTF-8 boundary within 1,000 bytes, normalize schemas and apply best-effort
  5,000-byte schema compaction. Unsupported schema keywords such as titles and
  defaults are not serialized.
- `tools/src/responses_api.rs`: serialize `strict: false`, omit output schemas
  and absent `defer_loading`; replace parameters with a permissive object when
  the **untagged function** exceeds 8,000 bytes. Report that fallback separately
  from schema preservation.
- `core/src/tools/handlers/mcp.rs`: truncate namespace instructions within 1,000
  bytes, then trim; wrap each function in its own namespace. Charge the full
  wrapper for **every tool**, before later namespace coalescing.
- `core/src/mcp_tool_exposure.rs`: enforce 8,000 bytes per wrapped spec and one
  64,000-byte accumulator across qualifying enabled agent plugins. Nonfitting
  tools become Hidden without consuming bytes; later smaller tools can fit.
  Deferred search does not bypass this admission check.

The simulator counts compact JSON serialized with `ensure_ascii=False`, UTF-8
encoding and JSON escaping. It models the reference-free schemas used here;
reference/definition schemas fail explicitly rather than being silently
mismeasured. Retained floats and integers outside i64/u64 are rejected rather
than approximating Rust serialization. Invalid retained field shapes, unknown
type names and explicit null fields are also outside the modeled subset;
`minItems` is conservatively limited to 32-bit unsigned values. Rejection means
unsupported by this simulator, not necessarily rejected by every native host.
Synthetic tests cover truncation/escaping, repeated namespace cost, schema
compaction/fallback, exact boundaries, multiple-plugin order and deferred exposure.

This is local simulation, not live discovery or model acceptance. Host order,
configured names, competing plugins and source classification affect exposure.
A registered `.app.json` alone does not establish agent-plugin classification.
There is no fixed tool-count limit or guaranteed allocation to Fulcra. Runtime
arguments/results, UI resources and skill bodies are outside this serialized
budget; keep longer workflows in skills while preserving essential safety and
routing in tool metadata and backend enforcement.

## Skill-first surface (1.17.0)

Compared with the unchanged 1.16.1 source at
`0a86795acd6f1f7df92aeb4a78287497a7266766`, using the same locked environment,
namespace `fulcra` and prod-mode command above:

- Model-visible tools: **39 → 30**. Nine domain operations move to app-only,
  one redundant opener is removed and one generic metadata updater is added.
- Candidate/charged bytes: **53,778 → 44,333**, a reduction of **9,445 (17.56%)**.
- Shared-budget headroom when measured alone: **19,667 bytes**; not reserved.
- Raw MCP tools JSON (including app-only tools): **46,513 → 47,276 bytes**.
  This increases because app operations remain callable and metadata update is new;
  it is not the model-facing context budget.
- Initialize instructions: **396 → 395 bytes**. No description/instruction truncation.

The remaining contact opener is `agent_contact_open`; canonical `send_agent_message`
and the separate `open_file_manager` remain model-visible. Native settings, UI
operations and mentions keep their app-only calls. This is a local working-tree
measurement, not a claim that the plugin or a native host loaded these tools.

## Historical description-compaction measurement

Baseline: merge revision `8acd245d0f84115dcbe7828ad277be8300d36c24`, incorporating
main `913e1e07cbc2e1595352e9a744592ed57ca760fd`. Metadata was captured **after the
merge and before shortening**. After: the metadata changes accompanying this
report. Locked environment: Python 3.14.7, FastMCP 3.4.7, MCP 1.28.1,
fulcra-api 0.1.53, Pydantic 2.13.4. Both measurements use namespace `fulcra`.

The actual baseline still had an experimental server filter: 31 model-visible
tools, totaling 62,268 bytes. The comparison below restores its eight filtered
consolidated tools using their real baseline definitions, so it compares the
**same full surface**, not a smaller inventory against a larger one.

To reproduce that projection, capture `Client(mcp).list_tools()` and initialize
instructions at the baseline revision; also capture
`Client(tools_mcp).list_tools()`. Combine by tool name, with composed-server
entries taking precedence. Save the combined tools and original instructions
as an inventory, then pass it to the current script with `--codex --inventory`.
No backend calls or user credentials are needed. Do not describe this projection
as the inventory actually advertised by the filtered baseline.

- Full-surface candidate bytes: **78,701 → 53,778** (24,923 fewer; 31.67%).
- Model-visible tools: **39 → 39**. After: all admitted when measured alone.
- Function bytes: 36,854 → 35,799.
- Repeated namespace overhead: 41,847 → 17,979.
- Raw initialize instructions: **1,426 → 396 UTF-8 bytes**; after fits untruncated.
- Raw visible tools/list array JSON, excluding initialize: 42,901 → 41,846 bytes.
  This is `json.dumps(visible_tools, ensure_ascii=False, separators=(",", ":"))`
  encoded as UTF-8, including the array brackets and commas. Each entry is an
  MCP Tool `model_dump(by_alias=True, exclude_none=True)`.
- After: largest spec 2,739 bytes; zero generic fallbacks or compacted schemas.
- **10,222 bytes** remain in the shared accumulator when Fulcra is alone.
  Other enabled plugins can still cause tools to be hidden.

Obsolete unreleased-plugin tool aliases were removed from repeated instructions;
current skills use current tool names. Persisted markers and explicit-consent
requirements remain. Released legacy-mesh conversion/history support is unchanged.

In the supplied baseline projection order, nine tools were hidden and 63,835
bytes admitted; that hidden set is order-dependent. Aggregate candidate cost is
not. Actual filtered baseline versus complete after is 62,268 → 53,778 bytes
while restoring eight tools—not the equal-surface prose savings above.

Each row includes its repeated namespace wrapper. A star marks a tool excluded
by the baseline **server filter**, not by simulated host admission.

| Tool | Before full | After | Saved bytes |
|---|---:|---:|---:|
| agent_connection_send | 2835 | 2089 | 746 |
| agent_contact_open | 1682 | 975 | 707 |
| agent_contacts_open | 1470 | 739 | 731 |
| archive_data_type | 1563 | 951 | 612 |
| create_data_type | 3351 | 2739 | 612 |
| create_group * | 2611 | 1999 | 612 |
| create_share | 2871 | 2259 | 612 |
| delete_file | 1536 | 924 | 612 |
| delete_records | 1861 | 1249 | 612 |
| delete_share | 1653 | 1041 | 612 |
| fulcra_settings_read | 1313 | 701 | 612 |
| fulcra_settings_update | 1457 | 845 | 612 |
| get_calendar_events * | 2021 | 1409 | 612 |
| get_contact_preferences | 1594 | 982 | 612 |
| get_data_catalog | 2477 | 1865 | 612 |
| get_data_updates | 2341 | 1729 | 612 |
| get_groups * | 1818 | 1206 | 612 |
| get_location | 2622 | 2010 | 612 |
| get_records | 2465 | 1853 | 612 |
| get_sleep * | 2338 | 1726 | 612 |
| get_time_series * | 2462 | 1850 | 612 |
| get_user_info | 1345 | 733 | 612 |
| get_workouts * | 1769 | 1157 | 612 |
| join_group * | 1674 | 1062 | 612 |
| leave_group * | 1740 | 1128 | 612 |
| list_files | 1933 | 1321 | 612 |
| list_shares | 1743 | 1131 | 612 |
| match_agent_invitations | 1764 | 1044 | 720 |
| open_file_manager | 1682 | 1070 | 612 |
| prepare_agent_invitation | 1951 | 1173 | 778 |
| read_file | 2066 | 1454 | 612 |
| record_data | 2957 | 2345 | 612 |
| restore_data_type | 1391 | 779 | 612 |
| restore_file | 1451 | 839 | 612 |
| send_agent_message | 2808 | 2156 | 652 |
| set_contact_identifier | 1802 | 1094 | 708 |
| set_contact_preferences | 1712 | 1100 | 612 |
| set_contact_status | 2264 | 1355 | 909 |
| write_file | 2308 | 1696 | 612 |
| **Total** | **78701** | **53778** | **24923** |
