# Releasing

Releases are automated. A release is a PR that bumps the version; merging it publishes the package to PyPI and the server listing to the [official MCP Registry](https://registry.modelcontextprotocol.io) (`com.fulcradynamics/context`).

## Cutting a release

```bash
uv run python scripts/release.py bump 0.5.0
```

This updates three files: open a PR with them.
- `pyproject.toml`: the package version.
- `server.json`:
  - `packages[].version` is set to the same version;
  - the listing's own `version` gets the next patch release. Pass `--server-version` to choose it.
- `uv.lock`.

The listing version and the package version are independent numbers: keep the listing's going up from where it is.

On every PR, `.github/workflows/release-check.yml` checks that:
- `pyproject.toml` and `server.json` agree;
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
