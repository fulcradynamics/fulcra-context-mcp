import hashlib
import json
import secrets
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
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl

from .settings import settings

OIDC_SCOPES = ["openid", "profile", "name", "email"]

logger = structlog.getLogger(__name__)


class FulcraOAuthProvider(OAuthProvider):
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
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.state_mapping: dict[str, dict[str, str]] = {}
        # Maps MCP tokens to the underlying FulcraCredentials
        self.token_mapping: dict[str, FulcraCredentials] = {}
        self.refresh_token_mapping: dict[str, FulcraCredentials] = {}
        # Fulcra API credentials keyed by MCP client_id
        self.client_credentials: dict[str, FulcraCredentials] = {}

    # Access/refresh tokens (and their mapped FulcraCredentials) are persisted
    # to ``state_path`` so issued tokens survive a restart or redeploy. The
    # in-memory dicts above act as a cache in front of disk.

    def _token_record_path(self, kind: str, token: str) -> Path | None:
        """Resolve the on-disk path for a persisted token record.

        ``kind`` is ``"access_tokens"`` or ``"refresh_tokens"``. The token is a
        bearer secret, so it is hashed to form the filename rather than written
        into the object name.
        """
        digest = hashlib.sha256(token.encode()).hexdigest()
        path = (settings.state_path / kind / f"{digest}.json").resolve()
        if not path.is_relative_to(settings.state_path):
            return None
        return path

    def _save_token_record(
        self, kind: str, token: str, token_obj, creds: FulcraCredentials | None
    ) -> None:
        path = self._token_record_path(kind, token)
        if path is None:
            return
        record = {
            "token": token_obj.model_dump_json(),
            "credentials": creds.to_json() if creds else None,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        except Exception as exc:
            logger.error("failed to persist token record", kind=kind, exc_info=exc)

    def _load_token_record(
        self, kind: str, token: str
    ) -> tuple[str, FulcraCredentials | None] | None:
        """Return ``(token_json, credentials)`` from disk, or ``None`` if absent."""
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
        creds = (
            FulcraCredentials.from_json(record["credentials"])
            if record.get("credentials")
            else None
        )
        return record["token"], creds

    def _delete_token_record(self, kind: str, token: str) -> None:
        path = self._token_record_path(kind, token)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("failed to delete token record", kind=kind, exc_info=exc)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get OAuth client information."""

        client_filepath = (settings.state_path / f"{client_id}.json").resolve()

        if not client_filepath.is_relative_to(settings.state_path):
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

        client_filepath = (
            settings.state_path / f"{client_info.client_id}.json"
        ).resolve()

        if not client_filepath.is_relative_to(settings.state_path):
            return None

        try:
            with client_filepath.open(mode="w") as c:
                c.write(client_info.model_dump_json())
        except Exception as exc:
            logger.error("Caught exception while writing client info", exc_info=exc)

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

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")

        mcp_token = f"mcp_{secrets.token_hex(32)}"
        refresh_token_value = f"mcp_refresh_{secrets.token_hex(32)}"

        self.tokens[mcp_token] = AccessToken(
            token=mcp_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
        )

        self.refresh_tokens[refresh_token_value] = RefreshToken(
            token=refresh_token_value,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )

        creds = self.client_credentials.get(client.client_id)
        if creds:
            self.token_mapping[mcp_token] = creds
            self.refresh_token_mapping[refresh_token_value] = creds

        self._save_token_record(
            "access_tokens", mcp_token, self.tokens[mcp_token], creds
        )
        self._save_token_record(
            "refresh_tokens",
            refresh_token_value,
            self.refresh_tokens[refresh_token_value],
            creds,
        )

        del self.auth_codes[authorization_code.code]

        logger.info(
            "tokens_issued",
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            has_refresh_token=True,
            has_fulcra_credentials=creds is not None,
        )

        return OAuthToken(
            access_token=mcp_token,
            token_type="bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh_token_value,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load and validate an access token."""
        access_token = self.tokens.get(token)
        if not access_token:
            # Rehydrate from disk (e.g. after a restart or redeploy).
            record = self._load_token_record("access_tokens", token)
            if record is None:
                logger.warning("token_not_found", token_prefix=token[:12])
                return None
            token_json, creds = record
            access_token = AccessToken.model_validate_json(token_json)
            self.tokens[token] = access_token
            if creds is not None:
                self.token_mapping[token] = creds

        if access_token.expires_at and access_token.expires_at < time.time():
            logger.info(
                "token_expired",
                client_id=access_token.client_id,
                scopes=access_token.scopes,
                token_prefix=token[:12],
            )
            self.tokens.pop(token, None)
            self.token_mapping.pop(token, None)
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
            token_json, creds = record
            token_obj = RefreshToken.model_validate_json(token_json)
            self.refresh_tokens[refresh_token] = token_obj
            if creds is not None:
                self.refresh_token_mapping[refresh_token] = creds
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
            self.refresh_token_mapping.pop(refresh_token, None)
            self._delete_token_record("refresh_tokens", refresh_token)
            return None
        return token_obj

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        creds = self.refresh_token_mapping.get(refresh_token.token)

        # Clean up old refresh token (rotation)
        self.refresh_tokens.pop(refresh_token.token, None)
        self.refresh_token_mapping.pop(refresh_token.token, None)
        self._delete_token_record("refresh_tokens", refresh_token.token)

        new_mcp_token = f"mcp_{secrets.token_hex(32)}"
        new_refresh_token_value = f"mcp_refresh_{secrets.token_hex(32)}"
        resolved_scopes = scopes if scopes else refresh_token.scopes

        self.tokens[new_mcp_token] = AccessToken(
            token=new_mcp_token,
            client_id=client.client_id,
            scopes=resolved_scopes,
            expires_at=int(time.time()) + 3600,
        )

        self.refresh_tokens[new_refresh_token_value] = RefreshToken(
            token=new_refresh_token_value,
            client_id=client.client_id,
            scopes=resolved_scopes,
        )

        if creds:
            self.token_mapping[new_mcp_token] = creds
            self.refresh_token_mapping[new_refresh_token_value] = creds

        self._save_token_record(
            "access_tokens", new_mcp_token, self.tokens[new_mcp_token], creds
        )
        self._save_token_record(
            "refresh_tokens",
            new_refresh_token_value,
            self.refresh_tokens[new_refresh_token_value],
            creds,
        )

        logger.info(
            "tokens_refreshed",
            client_id=client.client_id,
            scopes=resolved_scopes,
            has_fulcra_credentials=creds is not None,
        )

        return OAuthToken(
            access_token=new_mcp_token,
            token_type="bearer",
            expires_in=3600,
            scope=" ".join(resolved_scopes),
            refresh_token=new_refresh_token_value,
        )

    async def revoke_token(
        self, token: str, token_type_hint: str | None = None
    ) -> None:
        """Revoke a token."""
        self.tokens.pop(token, None)
        self.token_mapping.pop(token, None)
        self.refresh_tokens.pop(token, None)
        self.refresh_token_mapping.pop(token, None)
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
