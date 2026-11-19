"""Auth0 sign-in for apps that receive the redirect on a loopback port.

Native apps such as Hermes plugins listen on ``http://127.0.0.1:<random
port>/<path>`` for the OAuth redirect (RFC 8252), but Auth0 matches callback
URLs exactly, port included. These routes stand between them: Auth0 redirects
to this server's fixed ``/hermes/callback``, which hands the code to the app's
loopback URL. The app keeps its own PKCE verifier and gets Auth0's tokens, so
nothing is stored here.
"""

import base64
import html
import json
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fulcra_api.core import FULCRA_OIDC_AUDIENCE, FULCRA_OIDC_DOMAIN

from .public_url import public_origin
from .settings import settings

router = APIRouter(prefix="/hermes")

_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


def _auth0(path: str) -> str:
    return f"https://{settings.fulcra_oidc_domain or FULCRA_OIDC_DOMAIN}{path}"


def _callback_url(request: Request) -> str:
    return f"{public_origin(request)}/hermes/callback"


def _loopback(uri: str | None) -> str:
    """``uri`` if it is an http loopback URL with a port, else a 400."""
    parsed = urllib.parse.urlsplit(uri or "")
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.port is None
        or parsed.username is not None
        or parsed.fragment
    ):
        raise HTTPException(400, "redirect_uri must be http://127.0.0.1:<port>/<path>")
    return uri


def _pack(redirect_uri: str, state: str) -> str:
    raw = json.dumps({"r": redirect_uri, "s": state}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unpack(state: str) -> tuple[str, str]:
    try:
        data = json.loads(base64.urlsafe_b64decode(state + "=" * (-len(state) % 4)))
        return _loopback(data["r"]), data["s"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid state")


@router.get("/authorize")
async def authorize(request: Request) -> Response:
    params = dict(request.query_params)
    redirect_uri = _loopback(params.get("redirect_uri"))
    if not params.get("code_challenge"):
        raise HTTPException(400, "PKCE code_challenge is required")
    # The app's loopback URL rides in the state Auth0 echoes back. It needs no
    # signature: the callback only ever redirects to a loopback URL, and the
    # code is useless without the verifier the app kept.
    params |= {
        "redirect_uri": _callback_url(request),
        "state": _pack(redirect_uri, params.get("state", "")),
    }
    params.setdefault("audience", settings.fulcra_api or FULCRA_OIDC_AUDIENCE)
    return RedirectResponse(_auth0("/authorize?" + urllib.parse.urlencode(params)), 302)


@router.get("/callback")
async def callback(request: Request) -> Response:
    params = dict(request.query_params)
    redirect_uri, state = _unpack(params.get("state", ""))
    target = redirect_uri + ("&" if "?" in redirect_uri else "?")
    target += urllib.parse.urlencode(params | {"state": state})
    if "error" in params:
        return RedirectResponse(target, 302)
    # Auth0 can't tell which app owns a loopback port, and an existing Auth0
    # session skips its login page, so the user confirms the hand-off here.
    return HTMLResponse(_CONFIRM_PAGE.format(target=html.escape(target)))


@router.post("/token")
async def token(request: Request) -> Response:
    form = dict(await request.form())
    if form.get("grant_type") == "authorization_code":
        _loopback(form.get("redirect_uri"))
        form["redirect_uri"] = _callback_url(request)
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        upstream = await client.post(_auth0("/oauth/token"), data=form)
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
        headers={"Cache-Control": "no-store"},
    )


_CONFIRM_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finish signing in</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 28rem; margin: 15vh auto; padding: 0 1rem; text-align: center; }}
a {{ display: inline-block; margin-top: 1rem; padding: .75rem 1.5rem; border-radius: .5rem; background: #111; color: #fff; text-decoration: none; }}
</style>
</head>
<body>
<h1>Finish signing in</h1>
<p>Continue only if you just started signing in to Fulcra from Hermes on this computer.</p>
<a href="{target}">Continue to Hermes</a>
</body>
</html>
"""
