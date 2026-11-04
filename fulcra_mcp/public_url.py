"""The origin clients reach this server on, taken from each request.

One deployment answers on several hostnames (a custom domain, its run.app URL,
tagged preview revisions), so the OAuth discovery documents, the login redirect
and file links are all built for the host the client actually used.
``OIDC_SERVER_URL`` still overrides that when set.
"""

from fastmcp.server.dependencies import get_http_request
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import settings

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _request_origin(request: Request) -> str:
    """The origin a request was sent to. TLS ends in front of a hosted container,
    so the app sees plain http there: only loopback hosts keep their scheme."""
    url = request.base_url
    if url.hostname not in _LOOPBACK_HOSTS:
        url = url.replace(scheme="https")
    return str(url).rstrip("/")


def public_origin() -> str:
    """This server's origin, with no trailing slash: ``OIDC_SERVER_URL`` if set,
    else the current request's host, else localhost when there is no request
    (a stdio server, or startup)."""
    if settings.oidc_server_url:
        return settings.oidc_server_url.rstrip("/")
    try:
        return _request_origin(get_http_request())
    except RuntimeError:
        return f"http://localhost:{settings.port}"


class PublicOriginMiddleware:
    """Corrects the auth responses built before any request existed.

    The SDK and fastmcp build the discovery documents (served under every mount)
    and the 401 challenge once at startup, from ``advertised_origin``. Those are
    rewritten here so they can't disagree with each other about the host.
    """

    def __init__(self, app: ASGIApp, advertised_origin: str):
        self.app = app
        self.advertised_origin = advertised_origin.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # This runs outside FastMCP's request context, so public_origin() can't
        # see the request here.
        override = (settings.oidc_server_url or "").rstrip("/")
        origin = override or _request_origin(Request(scope))
        if origin == self.advertised_origin:
            await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, self._rewriting_send(scope, send, origin))

    def _rewriting_send(self, scope: Scope, send: Send, origin: str) -> Send:
        is_discovery = "/.well-known/oauth-" in scope["path"]
        response_start: Message | None = None
        body = bytearray()

        async def rewriting_send(message: Message) -> None:
            nonlocal response_start
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                challenge = headers.get("www-authenticate")
                if challenge:
                    headers["www-authenticate"] = challenge.replace(self.advertised_origin, origin)
                if is_discovery:
                    response_start = message  # Content-Length depends on the new body.
                    return
            elif is_discovery and message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
                if message.get("more_body", False):
                    return
                rewritten = bytes(body).replace(self.advertised_origin.encode(), origin.encode())
                MutableHeaders(scope=response_start)["content-length"] = str(len(rewritten))
                await send(response_start)
                await send({"type": "http.response.body", "body": rewritten})
                return
            await send(message)

        return rewriting_send
