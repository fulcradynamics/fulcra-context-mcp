import os
import sys
import threading
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from fastmcp.exceptions import ToolError
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.middleware.auth_context import get_access_token

from .provider import aware, oauth_provider
from .settings import settings
from .user_agent import fulcra_api_kwargs


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

    # Reentrant: newer fulcra-api's refresh_access_token calls
    # refresh_credentials, and both are overridden here.
    _refresh_lock = threading.RLock()

    def refresh_access_token(self) -> bool:
        with self._refresh_lock:
            creds = self.fulcra_credentials
            if creds is not None and creds.access_token and not creds.is_expired():
                return True
            return super().refresh_access_token()

    def refresh_credentials(self):
        # Newer fulcra-api refreshes through this (an expiring token, or a
        # 401) instead of refresh_access_token. A refresh may be wanted even
        # though the token looks valid, so skip only if another thread
        # replaced the token while this one waited.
        creds = self.fulcra_credentials
        held = creds.access_token if creds is not None else None
        with self._refresh_lock:
            creds = self.fulcra_credentials
            if (
                creds is not None
                and creds.access_token != held
                and not creds.is_expired()
            ):
                return
            super().refresh_credentials()


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
    if creds.access_token is None or creds.access_token_expiration is None:
        return True
    expires_at = aware(creds.access_token_expiration)
    return expires_at - datetime.now(UTC) < REFRESH_MARGIN


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


# Device-code login for stdio runs on a background thread so the server keeps
# answering requests while the user signs in. State is guarded by _login_lock.
_login_lock = threading.Lock()
_login_thread: threading.Thread | None = None
_login_prompt: tuple[str, str] | None = None  # (uri, code)
# Why the last login attempt ended without credentials; reported once, then
# cleared so the next call starts a fresh attempt.
_login_error: str | None = None


def _run_stdio_login(api: FulcraAPI):
    global stdio_fulcra, _login_thread, _login_prompt, _login_error

    def _stderr_prompt(device_code: str, uri: str, code: str):
        global _login_prompt
        with _login_lock:
            _login_prompt = (uri, code)
        webbrowser.open_new_tab(uri)
        # stdout carries the JSON-RPC stream in stdio mode.
        print(
            f"Use your browser to log in to Fulcra. If a tab does not open "
            f"automatically, visit this URL: {uri}\n"
            f"Verify that the code displayed matches: {code}",
            file=sys.stderr,
        )

    error = None
    try:
        creds = api.oidc.authorize_via_device_flow(prompt_callback=_stderr_prompt)
        if creds:
            api.fulcra_credentials = creds
            _save_stdio_credentials(creds)
            stdio_fulcra = api
            logger.info("stdio_login_complete")
        else:
            error = "the sign-in expired or was not approved"
            logger.warning("stdio_login_failed")
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        logger.warning("stdio_login_error", exc_info=exc)
    finally:
        with _login_lock:
            _login_thread = None
            _login_prompt = None
            _login_error = error


def _stdio_login_pending() -> FulcraAPI:
    """Start (or join) the background device-code login and raise a ToolError
    saying where things stand. Never waits, since this runs on the event loop."""
    global _login_thread, _login_error
    with _login_lock:
        if _login_thread is None:
            error, _login_error = _login_error, None
            if error is not None:
                raise ToolError(
                    f"Fulcra sign-in failed: {error}. Call this tool again "
                    "to start a new sign-in."
                )
            _login_thread = threading.Thread(
                target=_run_stdio_login,
                args=(SynchronizedFulcraAPI(**fulcra_api_kwargs()),),
                daemon=True,
            )
            _login_thread.start()
        prompt = _login_prompt
    if prompt is None:
        raise ToolError(
            "Fulcra sign-in is starting; no login code is ready yet. Call "
            "this tool again in a few seconds."
        )
    uri, code = prompt
    raise ToolError(
        f"Not signed in to Fulcra. Ask the user to open {uri} and confirm the "
        f"code {code}, then call this tool again. Sign-in finishes in the "
        "background."
    )


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
                **fulcra_api_kwargs(),
            )
            return stdio_fulcra

        return _stdio_login_pending()

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
    return fulcra_for_grant(grant_id, creds, mcp_access_token.client_id)


def current_grant_id() -> str | None:
    """The grant (Fulcra login) behind the current request: ``"stdio"`` for a
    local server, ``None`` when the request carries no usable MCP token."""
    if settings.fulcra_environment == "stdio":
        return "stdio"
    token = get_access_token()
    if not token:
        return None
    resolved = oauth_provider.credentials_for_token(token.token)
    return resolved[0] if resolved else None


class GrantFulcraAPI(FulcraAPI):
    """A FulcraAPI for one hosted grant, whose token refresh holds the grant
    lock and first adopts a copy another instance already refreshed.

    The up-front refresh in fulcra_for_grant already does that. This covers
    refreshes fulcra-api starts itself mid-request: newer releases refresh
    and retry once when the API answers 401.
    """

    def __init__(self, grant_id: str, **kwargs):
        super().__init__(**kwargs)
        self.grant_id = grant_id

    def refresh_credentials(self):
        held = self.fulcra_credentials.access_token
        with oauth_provider.grant_lock(self.grant_id):
            creds = oauth_provider.reload_grant(self.grant_id)
            if (
                creds is not None
                and creds.access_token != held
                and not _needs_refresh(creds)
            ):
                self.fulcra_credentials = creds
                return
            super().refresh_credentials()


def fulcra_for_grant(
    grant_id: str, creds: FulcraCredentials, client_id: str | None = None
) -> FulcraAPI:
    """A `FulcraAPI` acting for one grant, its Fulcra token refreshed up front.

    Used for tool calls, and for requests that carry no MCP token but name a
    grant they were issued for (file download links)."""

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
            client_id=client_id,
            grant_id=grant_id,
            new_expires_at=str(new_creds.access_token_expiration),
        )

    fulcra = GrantFulcraAPI(
        grant_id,
        oidc_client_id=settings.oidc_client_id,
        oidc_domain=settings.fulcra_oidc_domain,
        oidc_audience=settings.fulcra_api,
        credentials=creds,
        refresh_callback=on_refresh,
        **fulcra_api_kwargs(),
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
                    "fulcra_refresh_failed", client_id=client_id, grant_id=grant_id
                )
                raise ToolError(SESSION_EXPIRED)

    return fulcra
