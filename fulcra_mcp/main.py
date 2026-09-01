import json

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastmcp import FastMCP
from mcp.server.session import ServerSession

from .settings import settings
from .provider import oauth_provider
from .tools import tools_mcp
from .logging_config import configure_logging

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


mcp_asgi_app = mcp.http_app(path="/")


app = FastAPI(lifespan=mcp_asgi_app.lifespan, debug=True)


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


app.add_middleware(OpenAIWorkaroundMiddleware)
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
