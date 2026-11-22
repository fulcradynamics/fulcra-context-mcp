"""Device authorization (RFC 8628) for MCP clients, brokering Auth0's device flow.

A client on a machine without a browser (``hermes mcp login fulcra --flow device``) gets a code to enter
on any device. This server asks Auth0 for a device code with a device-enabled Auth0 client
(``DEVICE_OIDC_CLIENT_ID``), keeps Auth0's device code to itself, and hands the MCP client its own
code. When the MCP client polls ``/token`` with the device_code grant, this server polls Auth0 once and,
after approval, stores the Auth0 credentials as a grant (``device-<id>``, refreshed with the same Auth0
client) and issues MCP tokens exactly as the browser flow does.

Off unless ``DEVICE_OIDC_CLIENT_ID`` is set: nothing is advertised and every request goes to the SDK.
The MCP SDK knows neither this grant nor clients that register only for it, so its token, registration
and metadata routes are wrapped at the ASGI level; anything else passes through unchanged.
"""

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
from base64 import b64decode

import structlog
from fulcra_api.core import FULCRA_OIDC_AUDIENCE, FULCRA_OIDC_DOMAIN, FulcraAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import settings
from .user_agent import fulcra_api_kwargs

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
GRANT_PREFIX = "device-"
PATH = "/device_authorization"
# Auth0 errors a polling client acts on; anything else is reported as invalid_grant.
POLL_ERRORS = {"authorization_pending", "slow_down", "access_denied", "expired_token"}
FINAL_ERRORS = {"access_denied", "expired_token"}

logger = structlog.getLogger(__name__)


def enabled() -> bool:
    return bool(settings.device_oidc_client_id)


def oidc_client_id(grant_id: str) -> str | None:
    """The Auth0 client that issued, and refreshes, a grant's credentials."""
    if grant_id.startswith(GRANT_PREFIX):
        return settings.device_oidc_client_id
    return settings.oidc_client_id


def _auth0() -> FulcraAPI:
    return FulcraAPI(
        oidc_client_id=settings.device_oidc_client_id,
        oidc_domain=settings.fulcra_oidc_domain or FULCRA_OIDC_DOMAIN,
        oidc_audience=settings.fulcra_api or FULCRA_OIDC_AUDIENCE,
        **fulcra_api_kwargs(),
    )


def _error(error: str, status: int = 400, description: str | None = None) -> JSONResponse:
    body = {"error": error} | ({"error_description": description} if description else {})
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- ASGI plumbing


async def _body(receive: Receive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            return bytes(body)


def _replay(body: bytes, receive: Receive) -> Receive:
    """A receive that yields ``body`` once, then defers to the real one (for disconnects)."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


def _with_length(scope: Scope, length: int) -> Scope:
    headers = [(k, v) for k, v in scope["headers"] if k.lower() != b"content-length"]
    return {**scope, "headers": headers + [(b"content-length", str(length).encode())]}


class _TokenRoute:
    """``/token``: the device_code grant is answered here, everything else by the SDK."""

    def __init__(self, provider, app: ASGIApp):
        self.provider, self.app = provider, app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = await _body(receive)
        form = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
        if form.get("grant_type") != DEVICE_GRANT:
            await self.app(scope, _replay(body, receive), send)
            return
        response = await poll(self.provider, Request(scope), form)
        await response(scope, receive, send)


class _RegisterRoute:
    """``/register``: a client registering only for the device grant (as Hermes's device login does) is
    registered as an ordinary client that may also use it, since the SDK requires authorization_code."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = await _body(receive)
        try:
            metadata = json.loads(body)
        except ValueError:
            metadata = None
        grants = metadata.get("grant_types") if isinstance(metadata, dict) else None
        if isinstance(grants, list) and DEVICE_GRANT in grants and "authorization_code" not in grants:
            metadata["grant_types"] = ["authorization_code", *grants]
            if not metadata.get("response_types"):
                metadata["response_types"] = ["code"]
            body = json.dumps(metadata).encode()
            scope = _with_length(scope, len(body))
        await self.app(scope, _replay(body, receive), send)


class _MetadataRoute:
    """Authorization server metadata, plus the device endpoint and grant."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        start: Message | None = None
        body = bytearray()

        async def capture(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            body.extend(message.get("body", b""))
            if message.get("more_body", False):
                return
            out = bytes(body)
            if start and start["status"] == 200:
                doc = json.loads(out)
                token = doc["token_endpoint"]
                doc["device_authorization_endpoint"] = token[: token.rindex("/")] + PATH
                doc["grant_types_supported"] = [*doc.get("grant_types_supported", []), DEVICE_GRANT]
                out = json.dumps(doc).encode()
                headers = [(k, v) for k, v in start["headers"] if k.lower() != b"content-length"]
                start = {**start, "headers": headers + [(b"content-length", str(len(out)).encode())]}
            await send(start)
            await send({"type": "http.response.body", "body": out})

        await self.app(scope, receive, capture)


def routes(provider, existing: list[Route]) -> list[Route]:
    """``existing`` with the token, registration and metadata routes wrapped, plus the device endpoint."""
    out = []
    for route in existing:
        if route.path == "/token":
            route = Route(route.path, _TokenRoute(provider, route.app), methods=route.methods)
        elif route.path == "/register":
            route = Route(route.path, _RegisterRoute(route.app), methods=route.methods)
        elif route.path.startswith("/.well-known/oauth-authorization-server"):
            route = Route(route.path, _MetadataRoute(route.app), methods=route.methods)
        out.append(route)

    async def device_authorization(request: Request) -> JSONResponse:
        return await start(provider, request)

    out.append(Route(PATH, device_authorization, methods=["POST"]))
    return out


# ---------------------------------------------------------------- the flow


async def _client(provider, request: Request, form: dict):
    """The registered client making this request (client_secret_post or _basic), or an error response."""
    client_id, secret = form.get("client_id"), form.get("client_secret")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            client_id, _, secret = b64decode(auth[6:]).decode().partition(":")
            client_id, secret = urllib.parse.unquote(client_id), urllib.parse.unquote(secret)
        except ValueError:
            return None, _error("invalid_client", 401)
    client = await provider.get_client(client_id) if client_id else None
    if client is None:
        return None, _error("invalid_client", 401)
    if client.client_secret and not hmac.compare_digest(client.client_secret, secret or ""):
        return None, _error("invalid_client", 401)
    if DEVICE_GRANT not in (client.grant_types or []):
        return None, _error("unauthorized_client", description="This client did not register for the device grant.")
    return client, None


def _record_path(provider, code: str):
    return provider._state_file("device_codes", hashlib.sha256(code.encode()).hexdigest() + ".json")


async def start(provider, request: Request) -> JSONResponse:
    """``POST /device_authorization`` (RFC 8628 section 3.1)."""
    form = dict(await request.form())
    client, error = await _client(provider, request, form)
    if error:
        return error
    try:
        auth0_code, complete_uri, user_code, expires_in, interval = await asyncio.to_thread(
            _auth0().oidc.get_device_code
        )
    except Exception as exc:
        logger.error("device_code_request_failed", client_id=client.client_id, exc_info=exc)
        return _error("server_error", 502, "Could not start the device sign-in.")
    code = secrets.token_urlsafe(32)
    path = _record_path(provider, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"client_id": client.client_id, "auth0_device_code": auth0_code,
                                "expires_at": time.time() + float(expires_in)}))
    logger.info("device_flow_started", client_id=client.client_id)
    parsed = urllib.parse.urlsplit(complete_uri)
    return JSONResponse(
        {
            "device_code": code,
            "user_code": user_code,
            "verification_uri": urllib.parse.urlunsplit((*parsed[:3], "", "")),
            "verification_uri_complete": complete_uri,
            "expires_in": int(expires_in),
            "interval": int(interval),
        },
        headers={"Cache-Control": "no-store"},
    )


async def poll(provider, request: Request, form: dict) -> JSONResponse:
    """``POST /token`` with the device_code grant (RFC 8628 section 3.4)."""
    client, error = await _client(provider, request, form)
    if error:
        return error
    path = _record_path(provider, form.get("device_code") or "")
    try:
        record = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return _error("invalid_grant")
    if record["client_id"] != client.client_id:
        return _error("invalid_grant")
    if time.time() >= record["expires_at"]:
        path.unlink(missing_ok=True)
        return _error("expired_token")
    try:
        creds = await asyncio.to_thread(
            _auth0().oidc.get_token, DEVICE_GRANT, {"device_code": record["auth0_device_code"]}
        )
    except urllib.error.HTTPError as exc:
        with exc:
            try:
                auth0_error = json.loads(exc.read()).get("error")
            except ValueError:
                auth0_error = None
        if auth0_error in FINAL_ERRORS:
            path.unlink(missing_ok=True)
        return _error(auth0_error if auth0_error in POLL_ERRORS else "invalid_grant")
    except Exception as exc:
        logger.error("device_token_request_failed", client_id=client.client_id, exc_info=exc)
        return _error("server_error", 502)
    path.unlink(missing_ok=True)
    grant_id = GRANT_PREFIX + secrets.token_hex(16)
    provider.grant_credentials[grant_id] = creds
    provider.save_grant(grant_id)
    from .provider import OIDC_SCOPES

    tokens = provider._issue_tokens(client.client_id, OIDC_SCOPES, grant_id)
    logger.info("device_flow_tokens_issued", client_id=client.client_id, grant_id=grant_id,
                has_refresh_token=creds.refresh_token is not None)
    return JSONResponse(tokens.model_dump(mode="json", exclude_none=True), headers={"Cache-Control": "no-store"})
