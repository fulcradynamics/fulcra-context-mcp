import structlog
import os
import sys
import webbrowser
from pathlib import Path
from .settings import settings
from .provider import oauth_provider
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.middleware.auth_context import get_access_token
from fastapi import HTTPException

logger = structlog.getLogger(__name__)

stdio_fulcra: FulcraAPI | None = None


def _get_credentials_path() -> Path:
    """Return the path for Fulcra credentials.
    TODO: Replace with FulcraCredentials built-in persistence when available.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "fulcra" / "credentials.json"


def _load_stdio_credentials() -> FulcraCredentials | None:
    try:
        return FulcraCredentials.from_json(_get_credentials_path().read_text())
    except Exception:
        return None


def _save_stdio_credentials(creds: FulcraCredentials):
    path = _get_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json())


def get_fulcra_object() -> FulcraAPI:
    """
    Get or create an active `FulcraAPI` object.
    """
    global stdio_fulcra

    if settings.fulcra_environment == "stdio":
        if stdio_fulcra is not None:
            return stdio_fulcra

        creds = _load_stdio_credentials()
        if creds is not None:

            def on_refresh(new_creds: FulcraCredentials):
                creds.access_token = new_creds.access_token
                creds.access_token_expiration = new_creds.access_token_expiration
                if new_creds.refresh_token:
                    creds.refresh_token = new_creds.refresh_token
                _save_stdio_credentials(creds)
                logger.info("stdio_credentials_refreshed")

            stdio_fulcra = FulcraAPI(
                credentials=creds,
                refresh_callback=on_refresh,
            )
            return stdio_fulcra

        # stdout carries the JSON-RPC stream in stdio mode, so the device-flow
        # prompt must go to stderr (FulcraAPI.authorize() prints to stdout).
        def _stderr_prompt(device_code: str, uri: str, code: str):
            webbrowser.open_new_tab(uri)
            print(
                f"Use your browser to log in to Fulcra. If a tab does not open "
                f"automatically, visit this URL: {uri}\n"
                f"Verify that the code displayed matches: {code}",
                file=sys.stderr,
            )

        stdio_fulcra = FulcraAPI()
        stdio_fulcra.fulcra_credentials = stdio_fulcra.oidc.authorize_via_device_flow(
            prompt_callback=_stderr_prompt
        )
        if stdio_fulcra.fulcra_credentials:
            _save_stdio_credentials(stdio_fulcra.fulcra_credentials)
        return stdio_fulcra

    mcp_access_token = get_access_token()
    if not mcp_access_token:
        raise HTTPException(401, "Not authenticated")
    creds = oauth_provider.token_mapping.get(mcp_access_token.token)
    if creds is None:
        raise HTTPException(401, "Not authenticated")

    def on_refresh(new_creds: FulcraCredentials):
        creds.access_token = new_creds.access_token
        creds.access_token_expiration = new_creds.access_token_expiration
        if new_creds.refresh_token:
            creds.refresh_token = new_creds.refresh_token
        # Keep the persisted record fresh so the refreshed Fulcra token
        # survives a redeploy instead of going stale on disk.
        stored = oauth_provider.tokens.get(mcp_access_token.token)
        if stored is not None:
            oauth_provider._save_token_record(
                "access_tokens", mcp_access_token.token, stored, creds
            )
        logger.info(
            "fulcra_token_refreshed",
            new_expires_at=str(new_creds.access_token_expiration),
        )

    return FulcraAPI(
        oidc_client_id=settings.oidc_client_id,
        oidc_domain=settings.fulcra_oidc_domain,
        oidc_audience=settings.fulcra_api,
        credentials=creds,
        refresh_callback=on_refresh,
    )
