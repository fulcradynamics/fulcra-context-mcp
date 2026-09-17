import json
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastmcp import FastMCP
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.session import ServerSession
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from .logging_config import configure_logging
from .provider import oauth_provider
from .settings import settings
from .tools import tools_mcp

configure_logging(settings.log_format)
logger = structlog.getLogger(__name__)


mcp = FastMCP(
    name="Fulcra Context Agent",
    instructions="""
    This server provides personal data retrieval tools.
    Always specify the time zone when using times as parameters.
    """,
    auth=oauth_provider,
)
mcp.mount(tools_mcp)


# Add CORS middleware for browser-based clients
cors_middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],  # public server; auth is bearer-token, not cookies
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        # Starlette's "*" does not cover Authorization — list headers explicitly.
        allow_headers=[
            "mcp-protocol-version",
            "mcp-session-id",
            "Authorization",
            "Content-Type",
        ],
        # Browser JS must read the session id from the initialize response.
        expose_headers=["mcp-session-id"],
    )
]

# Stateless: every POST is self-contained, so nothing is lost when Cloud Run
# replaces or redeploys the instance, and there is no per-session state to leak
# (stateful sessions were never released - claude.ai never sends DELETE - and
# the resulting memory growth recycled the instance every day or two, which in
# turn broke users' stored Fulcra credentials; see docs/disconnect-diagnosis.md).
# GET (server-initiated SSE stream) is not served in this mode; clients treat
# the 405 as "unsupported" per the MCP spec. None of our tools need it.
mcp_asgi_app = mcp.http_app(path="/", middleware=cors_middleware, stateless_http=True)


app = FastAPI(lifespan=mcp_asgi_app.lifespan, debug=True)

STATIC_DIR = Path(__file__).parent / "static"


# Glama's directory verifies ownership of the hosted server by fetching this
# file. It is a single explicit route rather than a StaticFiles mount because
# the fastmcp app mounted at "/" serves the OAuth discovery documents under the
# same /.well-known prefix, and a mount there would shadow them.
@app.get("/.well-known/glama.json", include_in_schema=False)
async def glama_manifest() -> Response:
    return FileResponse(
        STATIC_DIR / ".well-known" / "glama.json", media_type="application/json"
    )


# Listing icon for the MCP registry and connector directories (server.json
# points here). Self-hosted so the URL is stable; the marketing site's assets
# live on a hashed Webflow CDN path that changes whenever the image is replaced.
@app.get("/icon.png", include_in_schema=False)
async def icon() -> Response:
    return FileResponse(STATIC_DIR / "icon.png", media_type="image/png")


# RFC 9728 path-form discovery for the advertised /mcp endpoint. The fastmcp app
# is mounted at "/" so it only publishes the root-form document, which declares
# resource "<base>/". Clients that connect to <base>/mcp look for
# /.well-known/oauth-protected-resource/mcp first, and spec-strict ones compare
# the declared resource against the URL they connected to, so serve that
# document with the matching identifier.
for _route in create_protected_resource_routes(
    resource_url=AnyHttpUrl(f"{str(oauth_provider.base_url).rstrip('/')}/mcp"),
    authorization_servers=[oauth_provider.issuer_url],
    scopes_supported=oauth_provider.client_registration_options.valid_scopes,
):
    app.router.routes.append(_route)


@app.get("/callback")
async def callback_handler(request: Request) -> Response:
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(400, "Missing code or state parameter")

    try:
        redirect_uri = await oauth_provider.handle_callback(code, state)
        return RedirectResponse(status_code=302, url=redirect_uri)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error", exc_info=e)
    raise HTTPException(500, "Unexpected error")


# OpenAI sends an invalid token_endpoint_auth_method, so we ignore that with this
# middleware.
class OpenAIWorkaroundMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Rewrite /mcp to /mcp/ so the Starlette mount passes "/" to the sub-app
        if scope["path"] == "/mcp":
            scope = dict(scope, path="/mcp/")
        if scope["path"] == "/MCP":
            scope = dict(scope, path="/MCP/")

        if scope["path"] in ("/register", "/mcp/register", "/MCP/register"):
            logger.info(
                "Intercepted /register request (ASGI). Attempting to modify 'token_endpoint_auth_method'."
            )

            body_chunks = []
            more_body = True
            while more_body:
                message = await receive()
                if message["type"] != "http.request":
                    logger.warning(
                        f"Unexpected ASGI message type '{message['type']}' received while reading body for /register."
                    )

                    if (
                        not body_chunks and message.get("body") is None
                    ):  # No body part in first message
                        logger.warning(
                            "No body found in first message for /register. Bypassing modification."
                        )

                        # Need to make sure the message we just consumed is passed on
                        async def pass_through_receive():
                            yield message  # The message we just consumed
                            while True:
                                yield await (
                                    receive()
                                )  # Subsequent messages from original stream

                        await self.app(scope, pass_through_receive(), send)
                        return

                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)
                if message["type"] == "http.disconnect":  # Client disconnected
                    logger.warning(
                        "Client disconnected while reading body for /register."
                    )
                    return

            original_body_bytes = b"".join(body_chunks)
            new_body_bytes = original_body_bytes

            if original_body_bytes:
                try:
                    body_str = original_body_bytes.decode("utf-8")
                    data = json.loads(body_str)

                    if (
                        isinstance(data, dict)
                        and data.get("token_endpoint_auth_method")
                        == "client_secret_basic"
                    ):
                        data["token_endpoint_auth_method"] = "client_secret_post"
                        new_body_bytes = json.dumps(data).encode("utf-8")
                        # Removed the line: new_body_bytes = bytes() which was a bug
                        logger.info(
                            "Successfully modified 'token_endpoint_auth_method' to 'client_secret_post' for /register request (ASGI)."
                        )
                    else:
                        logger.info(
                            "'token_endpoint_auth_method' was not 'client_secret_basic' or key not present in /register request body (ASGI). No changes made."
                        )

                except json.JSONDecodeError:
                    logger.warning(
                        "Request body for /register was not valid JSON (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
                except UnicodeDecodeError:
                    logger.warning(
                        "Request body for /register could not be decoded as UTF-8 (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
                except Exception:
                    logger.error(
                        "An unexpected error occurred while trying to modify the request body for /register (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
            else:
                logger.info(
                    "Request body for /register is empty (ASGI). No modification attempted."
                )

            sent_synthetic_body = False

            async def new_receive_for_app():
                nonlocal sent_synthetic_body
                if not sent_synthetic_body:
                    sent_synthetic_body = True
                    return {
                        "type": "http.request",
                        "body": new_body_bytes,
                        "more_body": False,
                    }
                else:
                    return await receive()

            await self.app(scope, new_receive_for_app, send)

        else:
            await self.app(scope, receive, send)


MCP_PATHS = ("/", "/mcp", "/mcp/", "/MCP", "/MCP/")


class MCPErrorLoggingMiddleware:
    """Log the body of 4xx responses on the MCP endpoint.

    The transport returns JSON-RPC errors for bad requests without logging why;
    the Cloud Run request log only shows the status. A small bounded capture
    makes "why does this client get 400s" answerable from logs.
    """

    MAX_BODY = 1024

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in MCP_PATHS:
            await self.app(scope, receive, send)
            return

        status = 0
        chunks: list[bytes] = []
        captured = 0

        async def logging_send(message):
            nonlocal status, captured
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and 400 <= status < 500:
                body = message.get("body", b"")
                if captured < self.MAX_BODY:
                    chunks.append(body[: self.MAX_BODY - captured])
                    captured += len(body)
                if not message.get("more_body", False):
                    logger.warning(
                        "mcp_http_client_error",
                        status=status,
                        method=scope.get("method"),
                        path=scope["path"],
                        body=b"".join(chunks).decode("utf-8", errors="replace"),
                    )
            await send(message)

        await self.app(scope, receive, logging_send)


app.add_middleware(OpenAIWorkaroundMiddleware)
app.add_middleware(MCPErrorLoggingMiddleware)
app.mount("/MCP", mcp_asgi_app)
app.mount("/mcp", mcp_asgi_app)
app.mount("/", mcp_asgi_app)


old__received_request = ServerSession._received_request


async def _received_request(self, *args, **kwargs):
    try:
        return await old__received_request(self, *args, **kwargs)
    except RuntimeError:
        logger.debug("Ignoring RuntimeError in _received_request", exc_info=True)


# pylint: disable-next=protected-access
ServerSession._received_request = _received_request


def main():
    if settings.fulcra_environment == "stdio":
        mcp.run()
    else:
        settings.state_path.mkdir(parents=True, exist_ok=True)

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=settings.port,
            access_log=settings.log_format != "json",
        )


if __name__ == "__main__":
    main()
