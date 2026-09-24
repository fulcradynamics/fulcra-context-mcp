import os
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import structlog
from fastmcp.exceptions import ToolError
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.middleware.auth_context import get_access_token

from .provider import oauth_provider
from .settings import settings


class SynchronizedFulcraAPI(FulcraAPI):
    """A FulcraAPI whose token refresh is serialized across threads.

    Used for the stdio singleton: tool calls can run in worker threads
    concurrently (e.g. the get_data_updates fan-out) while sharing one
    credentials object. Refresh tokens rotate, so two simultaneous refreshes
    of the same token would race and could invalidate the grant. Under the
    lock the expiry is re-checked, so a thread that lost the race reuses the
    winner's fresh token instead of refreshing again.

    Hosted mode does not use this: it refreshes up front under the per-grant
    lock with a margin (see get_fulcra_object), and this class's is_expired
    short-circuit would skip that early refresh.
    """

    _refresh_lock = threading.Lock()

    def refresh_access_token(self) -> bool:
        with self._refresh_lock:
            creds = self.fulcra_credentials
            if creds is not None and creds.access_token and not creds.is_expired():
                return True
            return super().refresh_access_token()


logger = structlog.getLogger(__name__)

stdio_fulcra: FulcraAPI | None = None

NOT_CONNECTED = (
    "This session is not connected to a Fulcra account. Reconnect the Fulcra "
    "connector (sign in again) and retry."
)
SESSION_EXPIRED = (
    "The Fulcra sign-in behind this connector has expired and could not be "
    "renewed. Reconnect the Fulcra connector (sign in again) and retry."
)

# Refresh this long before the Fulcra token expires. Otherwise a token that
# runs out during the request is refreshed lazily inside fulcra-api, outside
# the grant lock and with failures swallowed.
REFRESH_MARGIN = timedelta(seconds=120)


def _needs_refresh(creds: FulcraCredentials) -> bool:
    # Naive datetimes on purpose: fulcra-api stamps and compares expirations
    # with datetime.now() (see FulcraCredentials.is_expired), so a tz-aware
    # comparison here would raise.
    if creds.access_token is None or creds.access_token_expiration is None:
        return True
    return creds.access_token_expiration - datetime.now() < REFRESH_MARGIN  # noqa: DTZ005


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

            stdio_fulcra = SynchronizedFulcraAPI(
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

        stdio_fulcra = SynchronizedFulcraAPI()
        stdio_fulcra.fulcra_credentials = stdio_fulcra.oidc.authorize_via_device_flow(
            prompt_callback=_stderr_prompt
        )
        if stdio_fulcra.fulcra_credentials:
            _save_stdio_credentials(stdio_fulcra.fulcra_credentials)
        return stdio_fulcra

    mcp_access_token = get_access_token()
    if not mcp_access_token:
        raise ToolError(NOT_CONNECTED)
    resolved = oauth_provider.credentials_for_token(mcp_access_token.token)
    if resolved is None:
        # The MCP token is valid but was issued without Fulcra credentials
        # (login state lost mid-sign-in) or its grant file is unreadable.
        logger.warning(
            "fulcra_credentials_missing", client_id=mcp_access_token.client_id
        )
        raise ToolError(NOT_CONNECTED)
    grant_id, creds = resolved

    def on_refresh(new_creds: FulcraCredentials):
        # ``creds`` is the one shared object for this grant; update it in place
        # and persist the grant so the refreshed Fulcra token survives a
        # restart for every MCP token that points at it.
        creds.access_token = new_creds.access_token
        creds.access_token_expiration = new_creds.access_token_expiration
        if new_creds.refresh_token:
            creds.refresh_token = new_creds.refresh_token
        oauth_provider.save_grant(grant_id)
        logger.info(
            "fulcra_token_refreshed",
            client_id=mcp_access_token.client_id,
            grant_id=grant_id,
            new_expires_at=str(new_creds.access_token_expiration),
        )

    fulcra = FulcraAPI(
        oidc_client_id=settings.oidc_client_id,
        oidc_domain=settings.fulcra_oidc_domain,
        oidc_audience=settings.fulcra_api,
        credentials=creds,
        refresh_callback=on_refresh,
    )

    # fulcra-api refreshes lazily inside each request and swallows Auth0
    # errors, then sends the expired token anyway. Refresh up front instead,
    # serialised per grant, and fail with a message the user can act on.
    with oauth_provider.grant_lock(grant_id):
        if _needs_refresh(creds):
            # Another instance may already have refreshed this grant; its
            # copy is on disk and our cached refresh token may be rotated out.
            oauth_provider.reload_grant(grant_id)
        if _needs_refresh(creds):
            try:
                refreshed = fulcra.refresh_access_token()
            except Exception as exc:
                logger.warning("fulcra_refresh_error", grant_id=grant_id, exc_info=exc)
                refreshed = False
            if not refreshed:
                logger.warning(
                    "fulcra_refresh_failed",
                    client_id=mcp_access_token.client_id,
                    grant_id=grant_id,
                )
                raise ToolError(SESSION_EXPIRED)

    return fulcra
