# Development Plan: Interactive Setup Wizard for Fulcra MCP

*Implementation guide for the `fulcra-context-mcp init` command, aligned with the upstream `fulcra-context-mcp` and `fulcra-api-python` implementations.*

## Project Overview

Implement a CLI command — `fulcra-context-mcp init` (exposed from the existing Python package) — that guides a user through picking a connection mode, writing a correct MCP client config, and verifying the connection works. The wizard replaces copy-pasting JSON from the docs, reduces support burden, and catches misconfigurations early.

Fulcra's MCP server ships as a Python package on PyPI and is typically run via `uvx`. Two connection modes are supported and documented: a remote server at `https://mcp.fulcradynamics.com/mcp` accessed through the `mcp-remote` proxy, and a local stdio server launched via `uvx fulcra-context-mcp@latest`. Authentication is handled downstream — the remote server performs its own OAuth2 handshake on first client connection, and the local server uses the Python library's Auth0 Device Authorization Flow (token is held in-memory only; no disk persistence). The wizard does not need to implement an OAuth flow itself.

## Phase 1: CLI Infrastructure

### Task 1.1 — Dependency Integration
Add to `pyproject.toml`:
- `questionary` (or `prompt_toolkit`) — interactive TUI
- `pydantic` — config schema validation
- `rich` — formatted terminal output (likely already present; confirm)

`webbrowser` is stdlib — no dependency needed.

### Task 1.2 — Command Registration
Register an `init` subcommand via the package's existing entry point (`pyproject.toml` `[project.scripts]`). The subcommand is parsed before any MCP server startup logic runs and exits cleanly when finished.

Invocation: `uvx fulcra-context-mcp init` (no install required).

## Phase 2: Environment Detection & Mode Selection

### Task 2.1 — Runtime Discovery
Probe for available tooling, in priority order:
1. `uvx` (preferred — already how the server ships)
2. `uv` (fallback; can invoke `uv tool run`)
3. `npx` (required only if the user picks the remote mode via `mcp-remote`)
4. `pipx` (secondary fallback for local mode)

Record what's available. If none of `uvx`/`uv`/`pipx` are present and the user wants local mode, surface a clear install pointer (`https://docs.astral.sh/uv/`).

### Task 2.2 — Mode Selection
Present two options with clear tradeoffs:
- **Remote (recommended)** — `https://mcp.fulcradynamics.com/mcp` via `mcp-remote`. First client connection opens a browser for Auth0 login. Requires `npx`.
- **Local** — `uvx fulcra-context-mcp@latest` runs the server in-process over stdio. Auth uses the Python library's device flow on first API call; token is cached by the library.

Default to remote if `npx` is detected, otherwise local. Explain the choice before recommending it.

### Task 2.3 — ~~Optional Local Pre-Authorization~~ (Removed)
~~For local mode only, offer to pre-run the device flow so the first MCP tool call doesn't stall waiting on a browser.~~

**Finding:** `fulcra-api-python` stores tokens **only in-memory** (class-level variables on `FulcraAPI`). There is no disk persistence — no file, no keyring, no XDG cache. A token obtained during the wizard process cannot survive into the separately-spawned MCP server process. Pre-authorization is therefore **not useful** in the current architecture.

**Action:** Skip this task entirely. The first MCP tool call in local mode will always trigger the device flow. Mention this expected behavior in the Task 4.3 summary output so users aren't surprised. Revisit if `fulcra-api-python` adds disk-based token persistence (see `fulcra-api-recommendations.md`).

## Phase 3: Client Config Injection

### Task 3.1 — Client & Path Resolution
Support at minimum:
- **Claude Desktop** — `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), `%APPDATA%\Claude\claude_desktop_config.json` (Windows), `~/.config/Claude/claude_desktop_config.json` (Linux)
- **Cursor** — `~/.cursor/mcp.json`
- **Windsurf, VS Code, codename goose** — listed as tested in the docs; add as capacity allows

Structure path resolution as a registry (one entry per client) keyed by client name, so adding a new client is a single dict entry. Ask the user which client(s) to configure — allow multi-select.

### Task 3.2 — Safe JSON Update
Read → parse → merge → write with these guarantees:
- Back up the existing config to `<name>.bak-<timestamp>` before any write.
- Write to a temp file in the same directory, `fsync`, then `os.replace` over the original (atomic on POSIX and Windows).
- If the existing file is corrupted (invalid JSON), stop and show the user the exact parse error plus the backup path. Do not overwrite.
- If a `fulcra_context` entry already exists, diff it against what we'd write and ask: overwrite, keep existing, or abort.
- Preserve all other `mcpServers` entries and any unrelated top-level keys byte-for-byte where possible (round-trip through `json` with `indent=2`; document the formatting side-effect).

### Task 3.3 — Config Payload (Remote Mode)
```json
{
  "mcpServers": {
    "fulcra_context": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.fulcradynamics.com/mcp"]
    }
  }
}
```

### Task 3.4 — Config Payload (Local Mode)
```json
{
  "mcpServers": {
    "fulcra_context": {
      "command": "uvx",
      "args": ["fulcra-context-mcp@latest"]
    }
  }
}
```

No `env` block with secrets in either case — auth is handled downstream by the server or the Python library.

## Phase 4: Validation & Smoke Test

### Task 4.1 — Static Validation
Re-read the written config, parse it, and validate the `fulcra_context` block against a `pydantic` schema (correct `command`, correct args shape, no stray keys). Fail loudly if the round-trip doesn't match expectations.

### Task 4.2 — Live Handshake
Spawn the configured command as a subprocess over stdio and drive an MCP `initialize` request plus `tools/list`. Success criteria:
- Process starts within 30s (first-time `uvx` runs may download the package).
- `initialize` returns a valid response with matching protocol version.
- `tools/list` returns a non-empty list.

On failure, capture stderr and surface it verbatim. Common failure modes to detect explicitly:
- Network unreachable (remote mode)
- `uvx`/`npx` not on PATH despite earlier probe
- Device-flow token not yet obtained (local mode) — this is expected on first use; inform user that the MCP client will prompt for browser login on first tool call

### Task 4.3 — Next Steps Summary
Print the final config path, the mode chosen, the client(s) updated, and the exact command to launch or restart the MCP client so the new config loads.

## Phase 5: Recovery, Re-Runs, and Uninstall

### Task 5.1 — Idempotent Re-Run
Running `init` a second time should detect prior setup and offer: reconfigure (pick a new mode), update (bump pinned version), or uninstall.

### Task 5.2 — Interrupt Handling
Ctrl-C at any point should restore the last `.bak` file if a write is in progress and exit non-zero.

### Task 5.3 — Uninstall
A `fulcra-context-mcp init --uninstall` path that removes the `fulcra_context` block from selected client configs (preserving everything else). No token cleanup is needed — `fulcra-api-python` has no on-disk token cache, and the remote server's MCP-layer tokens are ephemeral in-memory mappings that expire on their own. Note to the user that their Auth0 browser session remains active (they can log out at `https://fulcra.us.auth0.com` if desired).

## Resolved Questions

1. **Token cache location.** ✅ Resolved — `fulcra-api-python` has **no on-disk token cache**. Tokens are stored only in-memory as class-level variables (`fulcra_cached_access_token`, `fulcra_cached_access_token_expiration`, `fulcra_cached_refresh_token` in `fulcra_api/core.py`). No file, keyring, or XDG cache is used. This eliminates Task 2.3 (pre-auth is useless across processes) and simplifies Task 5.3 (no token files to clean up). See `fulcra-api-recommendations.md` for a suggestion to add disk-based persistence upstream.

2. **Remote-mode logout.** ✅ Resolved — The remote server implements `revoke_token()` (`main.py:250-255`) as part of the MCP OAuth provider interface, but it only deletes the **MCP-layer proxy token** from the in-memory `self.tokens` dict. It does **not** revoke the upstream Auth0 session. No HTTP endpoint for Auth0 `/oauth/revoke` is exposed. For `init --uninstall`: remove the config block and inform the user that the Auth0 browser session persists. See `fulcra-api-recommendations.md` for a suggestion to add proper Auth0 token revocation upstream.

3. **Client discovery.** ✅ Resolved — **Auto-detect installed clients, with full list as fallback.** Check for config directory existence at runtime. Show detected clients pre-selected at the top, then list remaining known clients (Claude Desktop, Cursor, Windsurf, VS Code, Codename Goose) below as unchecked options. This handles both "I have it installed" and "I'm about to install it" users.

4. **Pinned vs. floating versions.** ✅ Resolved — **Default to `@latest`, no prompt.** Both `AGENTS.md` and `README.md` consistently use `fulcra-context-mcp@latest`. The package is at v0.1.5 with no stability contract yet. Pinning adds friction for a product that wants seamless updates. Revisit at 1.0 or if users report breakage.
