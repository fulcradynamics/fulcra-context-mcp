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

## Latest measurement (1.17.0)

Against 1.16.1 (`0a86795`), same environment and namespace `fulcra`:

- Model-visible tools: **39 → 30** (nine contact operations made app-only, one
  opener removed, `update_data_type_metadata` added).
- Charged bytes: **53,778 → 44,333**, leaving **19,667 bytes** of shared headroom
  when Fulcra is the only plugin. Nothing is truncated.
- Raw MCP tools JSON, including app-only tools: 46,513 → 47,276 bytes. This is not
  the model-facing budget.

An earlier pass (1.16.1) shortened descriptions and server instructions on the same
39-tool surface: 78,701 → 53,778 bytes, with initialize instructions 1,426 → 396 bytes.
