# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Regression coverage for #16: the base _SessionStore and auth_middleware
behavior had no direct tests -- only higher-level features built on top of
them (admin gate, forced password change, server-side hashing) were tested,
each exercising just the slice of this surface it needed.
"""

import time

import pytest
from fastapi import Request
from fastapi.responses import PlainTextResponse

from orchestrate.server import auth as auth_module
from orchestrate.server.auth import _SessionStore, auth_middleware, _PUBLIC_AUTH_PATHS


def _make_request(path, token=None, method="GET", as_cookie=False):
    headers = []
    if token:
        if as_cookie:
            headers.append((b"cookie", f"session_token={token}".encode()))
        else:
            headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)


async def _call_next(request):
    return PlainTextResponse("ok")


class TestSessionStoreLifecycle:
    def test_create_returns_unique_tokens(self):
        store = _SessionStore()
        token1, _ = store.create("alice")
        token2, _ = store.create("alice")
        assert token1 != token2

    def test_validate_true_for_fresh_token(self):
        store = _SessionStore()
        token, _ = store.create("alice")
        assert store.validate(token) is True

    def test_validate_false_for_unknown_token(self):
        store = _SessionStore()
        assert store.validate("does-not-exist") is False

    def test_validate_false_for_empty_token(self):
        store = _SessionStore()
        assert store.validate("") is False
        assert store.validate(None) is False

    def test_validate_false_and_evicts_expired_token(self):
        store = _SessionStore()
        token, _ = store.create("alice")
        username, role, _ = store._tokens[token]
        store._tokens[token] = (username, role, time.time() - 1)
        assert store.validate(token) is False
        assert token not in store._tokens

    def test_get_username_returns_username_for_valid_token(self):
        store = _SessionStore()
        token, _ = store.create("alice")
        assert store.get_username(token) == "alice"

    def test_get_username_none_for_unknown_token(self):
        store = _SessionStore()
        assert store.get_username("does-not-exist") is None

    def test_get_username_none_for_empty_token(self):
        store = _SessionStore()
        assert store.get_username("") is None

    def test_revoke_removes_the_token(self):
        store = _SessionStore()
        token, _ = store.create("alice")
        store.revoke(token)
        assert store.validate(token) is False
        assert store.get_username(token) is None

    def test_revoke_unknown_token_is_a_no_op(self):
        store = _SessionStore()
        store.revoke("does-not-exist")  # must not raise


class TestPublicAuthPaths:
    def test_login_check_register_are_public(self):
        assert _PUBLIC_AUTH_PATHS == {
            "/rest/v1/orchestrate/auth/login",
            "/rest/v1/orchestrate/auth/check",
            "/rest/v1/orchestrate/auth/register",
        }


@pytest.mark.anyio
class TestAuthMiddleware:
    async def test_options_preflight_always_allowed(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        request = _make_request("/rest/v1/orchestrate/workflows", method="OPTIONS")
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 200

    async def test_external_api_requires_machine_auth(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        request = _make_request("/api/v1/orchestrate/sop")
        monkeypatch.setattr(auth_module, "get_conf", lambda: {"enable_https": "false"})
        monkeypatch.setenv("ORCH_API_TOKEN", "test-only-machine-token-at-least-32-bytes")
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 401

    async def test_bypasses_entirely_when_auth_disabled(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: False)
        request = _make_request("/rest/v1/orchestrate/workflows")
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 200

    @pytest.mark.parametrize("path", sorted(_PUBLIC_AUTH_PATHS))
    async def test_public_auth_paths_bypass_without_a_token(self, monkeypatch, path):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        request = _make_request(path)
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 200

    async def test_missing_token_on_protected_path_is_401(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        request = _make_request("/rest/v1/orchestrate/workflows")
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 401

    async def test_invalid_token_on_protected_path_is_401(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        request = _make_request("/rest/v1/orchestrate/workflows", token="not-a-real-token")
        response = await auth_middleware(request, _call_next)
        assert response.status_code == 401

    async def test_valid_token_on_protected_path_passes_through(self, monkeypatch):
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        store = auth_module.get_session_store()
        token, _ = store.create("alice")
        try:
            request = _make_request("/rest/v1/orchestrate/workflows", token=token)
            response = await auth_middleware(request, _call_next)
            assert response.status_code == 200
        finally:
            store.revoke(token)

    async def test_valid_token_via_cookie_passes_through(self, monkeypatch):
        """The session cookie is the primary path -- EventSource sends it
        automatically without needing a header or URL param."""
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        store = auth_module.get_session_store()
        token, _ = store.create("alice")
        try:
            request = _make_request("/rest/v1/orchestrate/workflows", token=token, as_cookie=True)
            response = await auth_middleware(request, _call_next)
            assert response.status_code == 200
        finally:
            store.revoke(token)

    async def test_query_param_token_no_longer_accepted(self, monkeypatch):
        """?access_token=... is the pre-migration scheme this replaces (see
        #39) -- it must not be honored anymore."""
        monkeypatch.setattr(auth_module, "is_auth_enabled", lambda: True)
        store = auth_module.get_session_store()
        token, _ = store.create("alice")
        try:
            scope = {
                "type": "http", "method": "GET",
                "path": "/rest/v1/orchestrate/workflows", "headers": [],
                "query_string": f"access_token={token}".encode(),
            }
            response = await auth_middleware(Request(scope), _call_next)
            assert response.status_code == 401
        finally:
            store.revoke(token)
