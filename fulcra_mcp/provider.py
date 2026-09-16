import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

import structlog
from fastapi import HTTPException
from fastmcp.server.auth.auth import OAuthProvider
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl

from .settings import settings

OIDC_SCOPES = ["openid", "profile", "name", "email"]

logger = structlog.getLogger(__name__)


def _is_newer(candidate: FulcraCredentials, current: FulcraCredentials) -> bool:
    """Whether ``candidate`` holds a later-expiring Fulcra access token."""
    if candidate.access_token_expiration is None:
        return False
    if current.access_token_expiration is None:
        return True
    return candidate.access_token_expiration > current.access_token_expiration


def _copy_credentials(src: FulcraCredentials, dst: FulcraCredentials) -> None:
    """Copy the token fields of ``src`` into ``dst`` without changing identity."""
    dst.access_token = src.access_token
    dst.access_token_expiration = src.access_token_expiration
    if src.refresh_token:
        dst.refresh_token = src.refresh_token
    dst.refresh_token_expiration = src.refresh_token_expiration
    dst.id_token = src.id_token
    dst.id_token_expiration = src.id_token_expiration


class FulcraOAuthProvider(OAuthProvider):
    """OAuth provider that fronts Fulcra's Auth0 login for MCP clients.

    Persistence model (``settings.state_path``):

    * ``<client_id>.json``              dynamic client registrations
    * ``grants/<grant_id>.json``        the Fulcra (Auth0) credentials obtained by one
                                        login. This is the *only* copy of those
                                        credentials; every MCP access/refresh token
                                        issued from that login points at it.
    * ``access_tokens/<sha256>.json``   ``{"token": <AccessToken>, "grant_id": ...}``
    * ``refresh_tokens/<sha256>.json``  ``{"token": <RefreshToken>, "grant_id": ...}``

    Older records embedded a private copy of the credentials in every token
    record instead. That meant a Fulcra token refresh only reached the access-
    token copy; after a restart the refresh-token path rehydrated the stale copy
    and the next MCP refresh propagated it, leaving the grant with an expired
    Auth0 token and an already-rotated Auth0 refresh token. Such legacy records
    are adopted into ``legacy-<client_id>`` grants on first load, the copy with
    the latest expiry winning (see ``_adopt_legacy_credentials``).

    The in-memory ``grant_credentials`` cache is per process. Cloud Run runs
    more than one instance around restarts and deploys, so a refresh made by
    another instance only exists on disk; ``reload_grant`` picks it up before
    this process tries to spend a refresh token that may already be rotated.
    """

    def __init__(
        self,
        issuer_url: AnyHttpUrl | str,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
        required_scopes: list[str] | None = None,
    ):
        super().__init__(
            base_url=settings.oidc_server_url,
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
            required_scopes=required_scopes,
        )
        # Login-flow state. Lives only in this process for the few seconds
        # between /authorize, /callback and /token.
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.state_mapping: dict[str, dict[str, str]] = {}
        self.client_credentials: dict[str, FulcraCredentials] = {}

        # In-memory cache in front of the on-disk token records.
        self.tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}

        # Fulcra credentials, exactly one object per grant, plus the token ->
        # grant indexes. Anything that needs the credentials for a token must go
        # through ``credentials_for_token`` so all paths share the same object.
        self.grant_credentials: dict[str, FulcraCredentials] = {}
        self.token_grant: dict[str, str] = {}
        self.refresh_grant: dict[str, str] = {}
        self._grant_locks: dict[str, threading.Lock] = {}
        self._grant_locks_guard = threading.Lock()

    # ------------------------------------------------------------------ paths

    def _state_file(self, *parts: str) -> Path | None:
        """Resolve a file under ``state_path``; ``None`` if it escapes it."""
        path = settings.state_path.joinpath(*parts).resolve()
        if not path.is_relative_to(settings.state_path.resolve()):
            return None
        return path

    def _token_record_path(self, kind: str, token: str) -> Path | None:
        """``kind`` is ``"access_tokens"`` or ``"refresh_tokens"``. The token is
        a bearer secret, so it is hashed to form the filename."""
        digest = hashlib.sha256(token.encode()).hexdigest()
        return self._state_file(kind, f"{digest}.json")

    def _grant_path(self, grant_id: str) -> Path | None:
        return self._state_file("grants", f"{grant_id}.json")

    # ----------------------------------------------------------------- grants

    def grant_lock(self, grant_id: str) -> threading.Lock:
        """Per-grant lock; hold it while refreshing the Fulcra token so two
        concurrent tool calls cannot both spend the same Auth0 refresh token."""
        with self._grant_locks_guard:
            lock = self._grant_locks.get(grant_id)
            if lock is None:
                lock = self._grant_locks[grant_id] = threading.Lock()
            return lock

    def save_grant(self, grant_id: str) -> bool:
        """Persist the in-memory credentials for ``grant_id``. Returns success."""
        creds = self.grant_credentials.get(grant_id)
        path = self._grant_path(grant_id)
        if creds is None or path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(creds.to_json())
            return True
        except Exception as exc:
            logger.error("failed to persist grant", grant_id=grant_id, exc_info=exc)
            return False

    def _load_grant(self, grant_id: str) -> FulcraCredentials | None:
        """Return the single credentials object for ``grant_id``, reading it from
        disk on first use."""
        creds = self.grant_credentials.get(grant_id)
        if creds is not None:
            return creds
        path = self._grant_path(grant_id)
        if path is None:
            return None
        try:
            creds = FulcraCredentials.from_json(path.read_text())
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error("failed to load grant", grant_id=grant_id, exc_info=exc)
            return None
        self.grant_credentials[grant_id] = creds
        return creds

    def _new_grant(self, creds: FulcraCredentials) -> str:
        grant_id = secrets.token_hex(16)
        self.grant_credentials[grant_id] = creds
        self.save_grant(grant_id)
        return grant_id

    def reload_grant(self, grant_id: str) -> FulcraCredentials | None:
        """Re-read ``grant_id`` from disk and adopt it if it is newer.

        Another instance may have refreshed the Fulcra token since this process
        cached the grant. The cached object is updated *in place* because every
        MCP token issued from the login shares it. Returns the cached object.
        """
        creds = self._load_grant(grant_id)
        path = self._grant_path(grant_id)
        if creds is None or path is None:
            return creds
        try:
            on_disk = FulcraCredentials.from_json(path.read_text())
        except FileNotFoundError:
            return creds
        except Exception as exc:
            logger.error("failed to reload grant", grant_id=grant_id, exc_info=exc)
            return creds
        if _is_newer(on_disk, creds):
            _copy_credentials(on_disk, creds)
            logger.info("fulcra_grant_reloaded", grant_id=grant_id)
        return creds

    def _adopt_legacy_credentials(
        self, creds: FulcraCredentials, client_id: str
    ) -> str:
        """Map credentials embedded in a pre-grant token record onto a grant.

        The id derives from the MCP client id (one connector install, one
        Fulcra user) so every legacy record of that client lands on the same
        grant, whichever record is loaded first. Records written before the
        last Fulcra refresh carry an already-rotated Auth0 refresh token, so
        when the grant already exists the copy with the later access-token
        expiry wins.
        """
        grant_id = f"legacy-{client_id}"
        existing = self._load_grant(grant_id)
        if existing is None:
            self.grant_credentials[grant_id] = creds
            self.save_grant(grant_id)
        elif _is_newer(creds, existing):
            _copy_credentials(creds, existing)
            self.save_grant(grant_id)
        return grant_id

    def credentials_for_token(self, token: str) -> tuple[str, FulcraCredentials] | None:
        """``(grant_id, credentials)`` for an MCP access token, or ``None``."""
        grant_id = self.token_grant.get(token)
        if grant_id is None:
            return None
        creds = self._load_grant(grant_id)
        if creds is None:
            return None
        return grant_id, creds

    # ---------------------------------------------------------- token records

    def _save_token_record(
        self, kind: str, token: str, token_obj, grant_id: str | None
    ) -> None:
        path = self._token_record_path(kind, token)
        if path is None:
            return
        record = {"token": token_obj.model_dump_json(), "grant_id": grant_id}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        except Exception as exc:
            logger.error("failed to persist token record", kind=kind, exc_info=exc)

    def _load_token_record(
        self, kind: str, token: str
    ) -> tuple[str, str | None] | None:
        """Return ``(token_json, grant_id)`` from disk, or ``None`` if absent.

        Legacy records carry ``credentials`` instead of ``grant_id``; they are
        adopted into a grant and rewritten in the new form.
        """
        path = self._token_record_path(kind, token)
        if path is None:
            return None
        try:
            record = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error("failed to load token record", kind=kind, exc_info=exc)
            return None

        grant_id = record.get("grant_id")
        if grant_id is None and record.get("credentials"):
            try:
                legacy = FulcraCredentials.from_json(record["credentials"])
            except Exception as exc:
                logger.error(
                    "failed to parse legacy credentials", kind=kind, exc_info=exc
                )
                return record["token"], None
            client_id = json.loads(record["token"]).get("client_id", "unknown")
            grant_id = self._adopt_legacy_credentials(legacy, client_id)
            logger.info("legacy_token_record_adopted", kind=kind, grant_id=grant_id)
            try:
                path.write_text(
                    json.dumps({"token": record["token"], "grant_id": grant_id})
                )
            except Exception as exc:
                logger.error(
                    "failed to rewrite legacy token record", kind=kind, exc_info=exc
                )
        return record["token"], grant_id

    def _delete_token_record(self, kind: str, token: str) -> None:
        path = self._token_record_path(kind, token)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("failed to delete token record", kind=kind, exc_info=exc)

    # --------------------------------------------------------------- clients

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get OAuth client information."""
        client_filepath = self._state_file(f"{client_id}.json")
        if client_filepath is None:
            return None
        try:
            with client_filepath.open(mode="r") as c:
                return OAuthClientInformationFull.model_validate_json(c.read())
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error("Caught exception while loading client info", exc_info=exc)
            return None

    async def register_client(self, client_info: OAuthClientInformationFull):
        """Register a new OAuth client."""
        logger.info(
            "client_registration",
            client_id=client_info.client_id,
            client_name=client_info.client_name,
            scope=client_info.scope,
            grant_types=client_info.grant_types,
            redirect_uris=[str(u) for u in client_info.redirect_uris],
        )
        client_filepath = self._state_file(f"{client_info.client_id}.json")
        if client_filepath is None:
            return
        try:
            with client_filepath.open(mode="w") as c:
                c.write(client_info.model_dump_json())
        except Exception as exc:
            logger.error("Caught exception while writing client info", exc_info=exc)

    # ------------------------------------------------------------ login flow

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        logger.info(
            "authorize_request",
            client_id=client.client_id,
            client_name=client.client_name,
            requested_scopes=params.scopes,
        )
        state = params.state or secrets.token_hex(16)
        self.state_mapping[state] = {
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": str(
                params.redirect_uri_provided_explicitly
            ),
            "client_id": client.client_id,
        }
        fulcra = FulcraAPI(
            oidc_client_id=settings.oidc_client_id,
            oidc_domain=settings.fulcra_oidc_domain,
            oidc_audience=settings.fulcra_api,
        )
        auth_url = fulcra.get_authorization_code_url(
            redirect_uri=f"{settings.oidc_server_url}/callback",
            state=state,
        )
        return auth_url

    async def handle_callback(self, code: str, state: str) -> str:
        state_data = self.state_mapping.get(state)
        if not state_data:
            raise HTTPException(400, "Invalid state parameter")

        redirect_uri = state_data["redirect_uri"]
        code_challenge = state_data["code_challenge"]
        redirect_uri_provided_explicitly = (
            state_data["redirect_uri_provided_explicitly"] == "True"
        )
        client_id = state_data["client_id"]

        fulcra = FulcraAPI(
            oidc_client_id=settings.oidc_client_id,
            oidc_domain=settings.fulcra_oidc_domain,
            oidc_audience=settings.fulcra_api,
        )
        try:
            fulcra.authorize_with_authorization_code(
                code=code,
                redirect_uri=f"{settings.oidc_server_url}/callback",
            )
            self.client_credentials[client_id] = fulcra.fulcra_credentials
            logger.info(
                "fulcra_credentials_stored",
                client_id=client_id,
                has_refresh_token=fulcra.fulcra_credentials.refresh_token is not None,
                expires_at=str(fulcra.fulcra_credentials.access_token_expiration),
            )

            new_code = f"mcp_{secrets.token_hex(16)}"
            auth_code = AuthorizationCode(
                code=new_code,
                client_id=client_id,
                redirect_uri=AnyHttpUrl(redirect_uri),
                redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
                expires_at=time.time() + 300,
                scopes=OIDC_SCOPES,
                code_challenge=code_challenge,
            )
            self.auth_codes[new_code] = auth_code
        except Exception as e:
            logger.error("oauth2 code exchange failure", exc_info=e)
            raise HTTPException(400, "failed to exchange code for token")

        del self.state_mapping[state]
        return construct_redirect_uri(redirect_uri, code=new_code, state=state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """Load an authorization code."""
        return self.auth_codes.get(authorization_code)

    # --------------------------------------------------------------- tokens

    def _issue_tokens(
        self, client_id: str, scopes: list[str], grant_id: str | None
    ) -> OAuthToken:
        mcp_token = f"mcp_{secrets.token_hex(32)}"
        refresh_token_value = f"mcp_refresh_{secrets.token_hex(32)}"

        self.tokens[mcp_token] = AccessToken(
            token=mcp_token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + 3600,
        )
        self.refresh_tokens[refresh_token_value] = RefreshToken(
            token=refresh_token_value,
            client_id=client_id,
            scopes=scopes,
        )
        if grant_id is not None:
            self.token_grant[mcp_token] = grant_id
            self.refresh_grant[refresh_token_value] = grant_id

        self._save_token_record(
            "access_tokens", mcp_token, self.tokens[mcp_token], grant_id
        )
        self._save_token_record(
            "refresh_tokens",
            refresh_token_value,
            self.refresh_tokens[refresh_token_value],
            grant_id,
        )
        return OAuthToken(
            access_token=mcp_token,
            token_type="bearer",
            expires_in=3600,
            scope=" ".join(scopes),
            refresh_token=refresh_token_value,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")

        creds = self.client_credentials.pop(client.client_id, None)
        if creds is None:
            # The /callback that stored them ran in another process (restart or
            # second instance mid-login). Issuing a token now would create a
            # grant that can never call the Fulcra API; make the client retry.
            logger.error("login_state_missing", client_id=client.client_id)
            del self.auth_codes[authorization_code.code]
            raise TokenError(
                "invalid_grant",
                "Sign-in state was lost before the token exchange; please connect again.",
            )

        grant_id = self._new_grant(creds)
        tokens = self._issue_tokens(
            client.client_id, authorization_code.scopes, grant_id
        )
        del self.auth_codes[authorization_code.code]

        logger.info(
            "tokens_issued",
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            grant_id=grant_id,
            has_refresh_token=True,
            has_fulcra_credentials=True,
        )
        return tokens

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load and validate an access token."""
        access_token = self.tokens.get(token)
        if not access_token:
            # Rehydrate from disk (e.g. after a restart or redeploy).
            record = self._load_token_record("access_tokens", token)
            if record is None:
                logger.warning("token_not_found", token_prefix=token[:12])
                return None
            token_json, grant_id = record
            access_token = AccessToken.model_validate_json(token_json)
            self.tokens[token] = access_token
            if grant_id is not None:
                self.token_grant[token] = grant_id

        if access_token.expires_at and access_token.expires_at < time.time():
            logger.info(
                "token_expired",
                client_id=access_token.client_id,
                scopes=access_token.scopes,
                token_prefix=token[:12],
            )
            self.tokens.pop(token, None)
            self.token_grant.pop(token, None)
            self._delete_token_record("access_tokens", token)
            return None

        logger.info(
            "token_validated",
            client_id=access_token.client_id,
            scopes=access_token.scopes,
            expires_at=access_token.expires_at,
            token_prefix=token[:12],
        )
        return access_token

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        token_obj = self.refresh_tokens.get(refresh_token)
        if not token_obj:
            # Rehydrate from disk (e.g. after a restart or redeploy).
            record = self._load_token_record("refresh_tokens", refresh_token)
            if record is None:
                logger.warning(
                    "refresh token not found", token_prefix=refresh_token[:12]
                )
                return None
            token_json, grant_id = record
            token_obj = RefreshToken.model_validate_json(token_json)
            self.refresh_tokens[refresh_token] = token_obj
            if grant_id is not None:
                self.refresh_grant[refresh_token] = grant_id
        if token_obj.client_id != client.client_id:
            logger.warning(
                "refresh_token_client_mismatch",
                expected=client.client_id,
                actual=token_obj.client_id,
            )
            return None
        if token_obj.expires_at is not None and token_obj.expires_at < time.time():
            logger.info("refresh_token_expired", client_id=client.client_id)
            self.refresh_tokens.pop(refresh_token, None)
            self.refresh_grant.pop(refresh_token, None)
            self._delete_token_record("refresh_tokens", refresh_token)
            return None
        return token_obj

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # The grant travels with the refresh token; the credentials themselves
        # are never copied, so a Fulcra refresh made through any earlier access
        # token is what the new tokens see.
        grant_id = self.refresh_grant.pop(refresh_token.token, None)

        # Clean up old refresh token (rotation)
        self.refresh_tokens.pop(refresh_token.token, None)
        self._delete_token_record("refresh_tokens", refresh_token.token)

        resolved_scopes = scopes if scopes else refresh_token.scopes
        tokens = self._issue_tokens(client.client_id, resolved_scopes, grant_id)

        logger.info(
            "tokens_refreshed",
            client_id=client.client_id,
            scopes=resolved_scopes,
            grant_id=grant_id,
            has_fulcra_credentials=grant_id is not None
            and self._load_grant(grant_id) is not None,
        )
        return tokens

    async def revoke_token(
        self, token: str, token_type_hint: str | None = None
    ) -> None:
        """Revoke a token. The grant file is left in place: other tokens from the
        same login may still reference it."""
        self.tokens.pop(token, None)
        self.token_grant.pop(token, None)
        self.refresh_tokens.pop(token, None)
        self.refresh_grant.pop(token, None)
        self._delete_token_record("access_tokens", token)
        self._delete_token_record("refresh_tokens", token)


oauth_provider = FulcraOAuthProvider(
    issuer_url=AnyHttpUrl(settings.oidc_server_url),
    client_registration_options=ClientRegistrationOptions(
        enabled=True,
        valid_scopes=OIDC_SCOPES,
        default_scopes=OIDC_SCOPES,
    ),
    required_scopes=["openid"],
)
