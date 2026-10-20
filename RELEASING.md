# Releasing

A version-bump PR merged to `main` publishes the package to PyPI and the
[official MCP Registry](https://registry.modelcontextprotocol.io)
(`com.fulcradynamics/context`). Hosted deployment is separate.

## 1.17.1 release notes

- Contacts UI v67 can replace every action control with teal monospace "Ask <host>
  to …" instructions and a copy button; nothing is sent to chat. Polling,
  matching, acknowledgement on open and selected-contact context continue, and
  hosts with `updateModelContext` also get a short general app context naming
  the suggested requests and their skills. Enabled only with
  `FULCRA_CONTACTS_CONTROLS=chat`; controls remain the default.

## 1.17.0 release notes

- Add [owned Event/Metric metadata updates](docs/data-type-metadata.md) with
  independent readback, raw exact-catalog metadata and private-store safeguards.
- Keep contact operations and native settings app-only; retain canonical
  `send_agent_message` for models. Requires skill-first plugin procedures.
- Consolidate contact launch on `agent_contact_open`, with optional exact
  peer/thread or a full unselected list. Preserve app-only global navigation,
  native mentions and the separate file manager; remove the compact launch.
- Ship contacts UI v63 with fullscreen-only OpenAI metadata. Generic bridge
  capabilities are separate; display-mode changes preserve selection and drafts.
- No user-data or existing-schedule migration. Refresh discovery and update the
  compatible plugin; hosted/native acceptance remains separate from local tests.

## Version bump

    uv run python scripts/release.py bump 1.1.1

This updates `pyproject.toml`, both versions in `server.json`, and `uv.lock`.
One version covers the package, registry, Server Card and running server.
Release checks require matching versions, a valid registry schema/listing and a
version increase for changes to `server.json` (published versions are immutable).

For contact UI changes, follow [the app's development and tests](docs/contacts-app.md#development-and-tests)
and keep the paired plugin in step ([interface](docs/connection-compatibility.md)).

## Automated publication

On pushes to `main`, `.github/workflows/release.yml` publishes missing versions:

1. Run tests, build and upload to PyPI with Trusted Publishing; tag `vX.Y.Z`
   and create a GitHub release.
2. Wait for PyPI's package description (including README's `mcp-name` marker),
   check listed URLs, publish with `mcp-publisher`, and verify the registry.
3. Wait for the separately deployed server's version at
   `https://mcp.fulcradynamics.com/mcp/server-card`. A timeout here does not undo
   successful PyPI/registry publication.

`server.json` owns the server name, title, description and links. The Server Card
and initialization use it through `fulcra_mcp/server_info.py`.
Both publish jobs use the `release` GitHub environment. After fixing a failure,
rerun the workflow; it resumes unpublished work. Unchanged versions do nothing.

## One-time setup and recovery

- PyPI Trusted Publisher: owner `fulcradynamics`, repository `fulcra-context-mcp`,
  workflow `release.yml`, environment `release`.
- The infrastructure repo manages the `main`-only environment and optional required
  reviewers in `tf/github/repos/fulcra-context-mcp/terragrunt.hcl` (`environments`).
- Set `MCP_PRIVATE_KEY` manually in that environment, not in tofu state or source.
  It is the hex-encoded Ed25519 private key matching the `MCPv1` DNS TXT record
  on `fulcradynamics.com`.

For recovery, run `python3 scripts/release.py plan` to see what remains unpublished,
then follow the publication commands in
[the release workflow](.github/workflows/release.yml).
