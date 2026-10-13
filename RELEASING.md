# Releasing

Releases are automated. A release is a PR that bumps the version; merging it publishes the package to PyPI and the server listing to the [official MCP Registry](https://registry.modelcontextprotocol.io) (`com.fulcradynamics/context`).

## Cutting a release

### Contact last assessments (1.5.0 / UI v35)

Adds optional own-connection status metadata, an independently verified narrow setter,
and compact list/detail display with honest unknown/partial aggregation. Pair with
plugin 0.4.0; refresh server discovery and reinstall. Existing scheduling permissions
do not expand automatically. Foreground polling stays read-only. Local SDK/stdio and
sandbox browser tests do not establish live backend/model/ChatGPT task acceptance;
see [the app contract](docs/mesh-app.md).

### Latest-message window (UI v34)

Threads open on a window anchored to the latest incoming and outgoing messages,
replacing the date picker; **Load more history** adds two weeks. The thread list previews
each contact's latest message. An in-flow 232px footer spacer plus safe-area insets
keeps history controls above the host composer; the through-date label shows the
earliest attempted date. These UI-only changes require no plugin change and are
retained alongside contact assessments in UI v35. Refresh server discovery.

### Original setup session (1.4.1 / UI v31)

Optional own-channel description metadata enables explicit original-session
navigation and a copyable contextual handoff, with unchanged no-link fallback.
Pair with plugin 0.3.1; refresh server discovery and reinstall. Host APIs cannot
target an arbitrary existing chat or transfer context by opening its URL; native
desktop/web acceptance remains required. See [app contract](docs/mesh-app.md).

### Mesh check settings (1.3.0 / settings UI v1)

Adds native read-only mesh-check settings and an explicit schedule-management
chat handoff. Pair with Fulcra plugin 0.2.10, refresh server discovery and reinstall
the plugin. Existing mesh UI v28 is unchanged. See [settings acceptance](docs/mesh-settings.md)
for host gates; this does not deploy a scheduler or verify notification delivery.

### Direct mesh messaging (1.2.0 / UI v28)

Adds model/app-visible `mesh_send` with authenticated own-outbox/peer grant checks,
unchanged v1 envelopes and independent readback. Global and conversation panels
share direct Send, optimistic reconciliation and a separate optional-message chat
handoff. Pair with Fulcra plugin 0.2.6, refresh the server connection and reinstall
the plugin. No deployment or live-account acceptance is implied by local tests;
see [the app contract and limitations](docs/mesh-app.md#shared-composer-and-direct-sending-resource-v28).

### Version bump

```bash
uv run python scripts/release.py bump 1.1.1
```

This sets the version in `pyproject.toml`, in `server.json` (both its `version` and `packages[].version`) and in `uv.lock`. Open a PR with them.

One version covers everything: the PyPI package, the registry listing, the Server Card and the version the running server reports to clients. They've matched since 1.1.0.

On every PR, `.github/workflows/release-check.yml` checks that:
- `pyproject.toml` and `server.json` have the same version;
- `server.json` passes the registry schema and `mcp-publisher validate`;
- any change to `server.json` raises its `version`. Published registry versions can't be republished, so an unbumped change would never reach the listing.

## What merging does

On every push to `main`, `.github/workflows/release.yml` publishes whatever isn't published yet. A push that changes neither version does nothing.

1. **PyPI**, if PyPI doesn't have the `pyproject.toml` version:
   1. run the tests;
   2. build, and upload with PyPI Trusted Publishing;
   3. tag `vX.Y.Z` and create a GitHub release.
2. **MCP Registry**, if the registry doesn't have the `server.json` version. This also runs when only `server.json` changed.
   1. Wait until PyPI serves the package version. The registry checks for the `mcp-name` marker from `README.md` in that exact version's description.
   2. Check that the URLs `server.json` lists respond.
   3. Publish with `mcp-publisher`, then confirm the registry lists the new version as latest.
3. **Server Card**: wait until the hosted server, which deploys from `main` separately, serves the new version at `https://mcp.fulcradynamics.com/mcp/server-card`. If this times out, the deploy is late or broken; PyPI and the registry are already published.

The server's name, title, description and links come from `server.json`. It's served as the Server Card (SEP-2127) and reported to clients when they connect (`fulcra_mcp/server_info.py`), so change them there.

Both publish jobs run in the `release` GitHub environment. If a step fails, fix the cause and re-run the workflow from the Actions tab ("Run workflow"); it picks up whatever is still unpublished.

## One-time setup

- **PyPI:** on the `fulcra-context-mcp` project, add a Trusted Publisher with:
  - owner `fulcradynamics`;
  - repository `fulcra-context-mcp`;
  - workflow `release.yml`;
  - environment `release`.
- **GitHub:** the `release` environment, limited to `main`, is managed in the infrastructure repo at `tf/github/repos/fulcra-context-mcp/terragrunt.hcl` (`environments`). Add required reviewers there if releases should wait for approval.
- **Registry key:** the environment secret `MCP_PRIVATE_KEY` is set by hand, so the key never enters tofu state: `gh secret set MCP_PRIVATE_KEY --env release -R fulcradynamics/fulcra-context-mcp`. Its value is the hex-encoded Ed25519 private key matching the `MCPv1` DNS TXT record on `fulcradynamics.com`; see `docs/registry-publishing.md` for how to derive it. Never commit the key.

## Publishing by hand

If the workflow can't run, the manual steps are in `docs/registry-publishing.md`. Run `python3 scripts/release.py plan` to see what's unpublished.
