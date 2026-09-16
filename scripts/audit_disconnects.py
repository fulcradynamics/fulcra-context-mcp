"""Reproduce outstanding remote-server defects using synthetic credentials.

Run from the repo root: uv run pytest scripts/audit_disconnects.py -q --tb=short

These assertions describe desired behavior and currently FAIL. This audit is
outside the default testpaths so the ordinary suite remains independently useful.
No network calls, real credentials, or production writes are made.
"""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
import sys
import threading
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_provider_persistence import (
    CLIENT, OIDC_SCOPES, creds_expiring_in, fresh_creds, login,
    make_provider, refresh, state_path, use_token, write_legacy_record,
)
import fulcra_mcp.credentials as credentials_module
import fulcra_mcp.provider as provider_module
from fastmcp.exceptions import ToolError
from fulcra_api.oidc import FulcraOIDCProvider
from mcp.server.auth.provider import AuthorizationParams
from fulcra_mcp.settings import settings


async def test_legacy_refresh_first_finds_latest_credentials(state_path):
    seed = make_provider()
    write_legacy_record(seed, 'refresh_tokens', 'old-refresh',
                        fresh_creds('stale', expired=True))
    write_legacy_record(seed, 'access_tokens', 'old-access', fresh_creds('latest'))
    restarted = make_provider()
    tokens = await refresh(restarted, 'old-refresh')
    _, creds = restarted.credentials_for_token(tokens.access_token)
    # The client uses its newly issued token, never the previous access token.
    assert creds.refresh_token == 'auth0-refresh-latest'


async def test_legacy_accounts_with_same_client_remain_isolated(state_path):
    seed = make_provider()
    write_legacy_record(seed, 'access_tokens', 'alice-mcp',
                        creds_expiring_in('alice', timedelta(hours=1)))
    write_legacy_record(seed, 'access_tokens', 'bob-mcp',
                        creds_expiring_in('bob', timedelta(hours=2)))
    p = make_provider()
    await p.load_access_token('alice-mcp')
    await p.load_access_token('bob-mcp')
    assert p.credentials_for_token('alice-mcp')[1].access_token == 'auth0-access-alice'


async def test_simultaneous_instance_refreshes_both_succeed(state_path, monkeypatch):
    monkeypatch.setattr(settings, 'fulcra_environment', 'prod')
    first, second = make_provider(), make_provider()
    tokens = await login(first, fresh_creds('old', expired=True))
    await second.load_access_token(tokens.access_token)
    use_token(monkeypatch, tokens.access_token)
    selected = ContextVar('audit_provider')
    class Proxy:
        def __getattr__(self, name):
            return getattr(selected.get(), name)
    monkeypatch.setattr(credentials_module, 'oauth_provider', Proxy())
    barrier = threading.Barrier(2)
    issuer_lock = threading.Lock()
    spent = set()
    def rotate(self, creds):
        token = creds.refresh_token
        barrier.wait(timeout=5)  # Both instances have read the old grant.
        with issuer_lock:
            if token in spent:
                raise RuntimeError('synthetic issuer: refresh token already spent')
            spent.add(token)
        return fresh_creds('new')
    monkeypatch.setattr(FulcraOIDCProvider, 'refresh_credentials', rotate)
    def call(p):
        selected.set(p)
        try:
            credentials_module.get_fulcra_object()
            return 'ok'
        except ToolError:
            return 'reconnect required'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, [first, second]))
    assert results == ['ok', 'ok'], results


async def test_callback_can_run_on_another_instance(state_path, monkeypatch):
    first, second = make_provider(), make_provider()
    fake = MagicMock()
    fake.get_authorization_code_url.return_value = 'https://example.com/authorize'
    fake.fulcra_credentials = fresh_creds('user')
    monkeypatch.setattr(provider_module, 'FulcraAPI', lambda **kwargs: fake)
    params = AuthorizationParams(
        state='login-state', scopes=OIDC_SCOPES, code_challenge='challenge',
        redirect_uri=CLIENT.redirect_uris[0], redirect_uri_provided_explicitly=True,
    )
    await first.authorize(CLIENT, params)
    await second.handle_callback('upstream-code', 'login-state')


async def test_authorization_code_can_be_loaded_on_another_instance(state_path, monkeypatch):
    first, second = make_provider(), make_provider()
    fake = MagicMock()
    fake.get_authorization_code_url.return_value = 'https://example.com/authorize'
    fake.fulcra_credentials = fresh_creds('user')
    monkeypatch.setattr(provider_module, 'FulcraAPI', lambda **kwargs: fake)
    params = AuthorizationParams(
        state='login-state', scopes=OIDC_SCOPES, code_challenge='challenge',
        redirect_uri=CLIENT.redirect_uris[0], redirect_uri_provided_explicitly=True,
    )
    await first.authorize(CLIENT, params)
    await first.handle_callback('upstream-code', 'login-state')
    code = next(iter(first.auth_codes))
    assert await second.load_authorization_code(CLIENT, code) is not None


async def test_revocation_invalidates_other_instance_cache(state_path):
    first, second = make_provider(), make_provider()
    tokens = await login(first, fresh_creds('user'))
    await second.load_access_token(tokens.access_token)
    await second.load_refresh_token(CLIENT, tokens.refresh_token)
    await first.revoke_token(tokens.access_token)
    await first.revoke_token(tokens.refresh_token)
    assert await second.load_access_token(tokens.access_token) is None
    assert await second.load_refresh_token(CLIENT, tokens.refresh_token) is None


async def test_rotation_does_not_succeed_with_unpersisted_replacement(state_path, monkeypatch):
    first = make_provider()
    tokens = await login(first, fresh_creds('user'))
    original_write = Path.write_text
    def failing_write(path, *args, **kwargs):
        if path.parent.name == 'refresh_tokens':
            raise OSError('synthetic shared-storage write failure')
        return original_write(path, *args, **kwargs)
    with monkeypatch.context() as m:
        m.setattr(Path, 'write_text', failing_write)
        replacements = await refresh(first, tokens.refresh_token)
    second = make_provider()
    assert await second.load_refresh_token(CLIENT, replacements.refresh_token) is not None
