# Upstream Recommendations for Fulcra Developers

*Findings from reviewing `fulcra-api-python` and `fulcra-context-mcp` while planning the `init` wizard. These are changes that would improve the developer/user experience but live in upstream repos.*

## 1. Add Disk-Based Token Persistence to `fulcra-api-python`

**Priority: High** — This is the single biggest gap affecting local-mode UX.

### Problem

`fulcra-api-python` stores OAuth tokens only in-memory (`fulcra_cached_access_token` and friends as class-level variables in `fulcra_api/core.py`). When the process exits, the token is gone. This means:

- Every new `uvx fulcra-context-mcp@latest` invocation triggers a fresh device authorization flow (browser popup + polling).
- The `init` wizard cannot pre-authorize on behalf of the MCP server — the token obtained in the wizard process dies when the wizard exits.
- Users of the Python library in scripts/notebooks must re-authorize every session.

### Security Analysis

The in-memory-only approach has a surface-level security argument: tokens on disk can be stolen by other local processes, malware, or anyone with filesystem access. Refresh tokens are especially sensitive since they're long-lived and can mint fresh access tokens, and because the Auth0 client (`48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt`) is a public/native app with no client secret, a stolen refresh token has no additional factor protecting it.

However, this argument does not hold up in context:

1. **The threat model already trusts the local machine.** The device flow opens the user's browser, relies on their Auth0 session cookies (which *are* persisted to disk by the browser), and trusts whatever process calls `authorize()`. An attacker with local file access could just call `FulcraAPI().authorize()` themselves.

2. **Every comparable CLI tool persists tokens.** `gh`, `gcloud`, `aws`, `az`, `docker`, `kubectl`, `heroku` — all write OAuth/credential tokens to disk. This is industry-standard practice for CLI tools targeting developer machines.

3. **`mcp-remote` already persists tokens to disk.** Users in remote mode are already getting tokens written to their filesystem by the `mcp-remote` npm proxy. Local mode is strictly worse UX for no additional security.

4. **Auth fatigue is itself a security risk.** Forcing repeated browser auth flows trains users to click through Auth0 prompts reflexively — the opposite of the intended effect.

5. **Standard mitigations exist.** `0600` file permissions, OS keychains (macOS Keychain, Linux Secret Service, Windows Credential Manager), and Auth0's refresh token rotation (each use invalidates the previous token) all reduce the risk to well-understood levels.

Most likely the in-memory-only approach is not a deliberate security decision — it's the simplest implementation for the library's original use case (single-session notebooks/scripts). Persistence wasn't added because the immediate use case didn't demand it.

### Recommendation

Add an opt-in disk-based token cache. Suggested approach:

```
~/.config/fulcra/tokens.json   (Linux/macOS, respecting XDG_CONFIG_HOME)
%APPDATA%\fulcra\tokens.json   (Windows)
```

Contents: `{ "access_token": "...", "refresh_token": "...", "expiration": "ISO8601" }` with `0600` file permissions.

API surface change:
```python
# Opt-in via constructor parameter (backwards-compatible)
fulcra = FulcraAPI(persist_tokens=True)

# Or environment variable for zero-code-change adoption
# FULCRA_PERSIST_TOKENS=1
```

On `authorize()` success, write the token to disk. On `FulcraAPI()` construction with `persist_tokens=True`, check for a cached token and load it if not expired (or attempt a refresh if a refresh token is present).

### Impact

- The `init` wizard could pre-authorize and the MCP server would pick up the token — eliminating the first-tool-call login stall.
- Notebook users would stay logged in across kernel restarts.
- Script users wouldn't need to re-auth every run.

---

## 2. Add Auth0 Token Revocation to the Remote MCP Server

**Priority: Medium** — Matters for proper logout/uninstall hygiene.

### Problem

The remote server's `FulcraOAuthProvider.revoke_token()` (`main.py:250-255`) only removes the MCP-layer proxy token from the in-memory `self.tokens` dict. It does **not** revoke the upstream Fulcra/Auth0 token that was exchanged during the OAuth callback flow.

This means:
- `init --uninstall` can remove the client config but cannot invalidate the server-side session.
- Users who want a clean logout have no programmatic path — they'd need to manually visit Auth0.
- The MCP protocol's revocation endpoint technically "works" but is semantically incomplete.

### Recommendation

In `FulcraOAuthProvider.revoke_token()`, after removing the proxy token, also call Auth0's token revocation endpoint:

```python
async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
    # Revoke the MCP-layer proxy token
    fulcra_token = self.tokens.pop(token, None)

    # Also revoke the upstream Auth0 token if we have it
    if fulcra_token:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://{OIDC_DOMAIN}/oauth/revoke",
                json={
                    "client_id": OIDC_CLIENT_ID,
                    "token": fulcra_token,
                },
            )
```

This requires maintaining the mapping from proxy tokens back to the Fulcra tokens they represent (the `self.tokens` dict already maps proxy → Fulcra tokens via the exchange flow, so the data is available).

### Auth0 Endpoint Reference

- **Revoke endpoint:** `POST https://fulcra.us.auth0.com/oauth/revoke`
- **Required params:** `client_id`, `token`
- **Docs:** https://auth0.com/docs/api/authentication#revoke-refresh-token

---

## 3. Request `offline_access` Scope in Device Flow

**Priority: Medium** — Needed for token persistence to be useful.

### Problem

The device authorization flow in `fulcra-api-python` requests scopes `openid profile name email` but does **not** request `offline_access`. Without this scope, Auth0 does not return a refresh token. The access token typically expires in 24 hours, after which the user must re-authorize from scratch.

Interestingly, `FULCRA_OIDC_SCOPE` in `core.py` defaults to `"openid profile name email offline_access"` — but the `_request_device_code` method hardcodes its own scope string rather than using this constant. And in `authorize()`, after a successful token exchange, `fulcra_cached_refresh_token` is explicitly set to `None`.

### Recommendation

1. Use the `FULCRA_OIDC_SCOPE` constant (which already includes `offline_access`) in the device code request.
2. Store the refresh token from the token response instead of discarding it.
3. Add a `refresh_access_token()` call path that uses the persisted refresh token before falling back to a new device flow.

This pairs with recommendation #1 (disk persistence) — a refresh token on disk means users re-auth only when the refresh token itself is revoked, not every 24 hours.

---

## 4. Expose Auth0 Configuration Constants

**Priority: Low** — Quality-of-life for downstream consumers.

### Problem

The Auth0 domain (`fulcra.us.auth0.com`), client ID (`48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt`), and audience (`https://api.fulcradynamics.com/`) are defined as module-level variables in `fulcra_api/core.py` but are not part of the public API surface. External tools (like the `init` wizard's uninstall message, or third-party integrations) that need to reference these values must either hardcode them or import private internals.

### Recommendation

Export these as public constants:

```python
# fulcra_api/constants.py (or top-level __init__.py)
FULCRA_AUTH0_DOMAIN = "fulcra.us.auth0.com"
FULCRA_OIDC_CLIENT_ID = "48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt"
FULCRA_API_AUDIENCE = "https://api.fulcradynamics.com/"
```

This also makes it clearer to auditors/reviewers that these are intentionally public values (client IDs for native/device apps are not secrets).

---

## Summary

| # | Recommendation | Repo | Priority | Unlocks |
|---|---|---|---|---|
| 1 | Disk-based token persistence | `fulcra-api-python` | High | Pre-auth in wizard, persistent sessions |
| 2 | Auth0 token revocation | `fulcra-context-mcp` | Medium | Clean logout/uninstall |
| 3 | `offline_access` scope + refresh tokens | `fulcra-api-python` | Medium | Long-lived sessions |
| 4 | Export Auth0 constants | `fulcra-api-python` | Low | Cleaner downstream integrations |

Recommendations 1 and 3 are complementary — disk persistence is most valuable when combined with refresh tokens. Implementing both together would give local-mode users a "log in once, stay logged in" experience comparable to remote mode.
