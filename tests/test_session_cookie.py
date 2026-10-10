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

"""Regression coverage for 9b: the session token moved from a JSON body
field (stored client-side in localStorage) to an httpOnly cookie.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from orchestrate.server import auth as auth_module
from orchestrate.server import frontend_support_server as srv
from orchestrate.server.auth import SESSION_COOKIE_NAME, SESSION_COOKIE_PATH

BASE = "/rest/v1/orchestrate"


def _file_mode_conf(password: str, enable_https: str = "false") -> dict:
    stored_hash = hashlib.sha256(password.encode()).hexdigest()
    return {"persistence_mode": "file", "access_password": stored_hash, "enable_https": enable_https}


@pytest.fixture
def client():
    with TestClient(srv.app) as c:
        yield c


class TestLoginSetsSessionCookie:
    def test_cookie_is_httponly_samesite_lax_scoped_to_internal_api(self, client, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!")
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)

        resp = client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})

        assert resp.status_code == 200
        assert resp.cookies.get(SESSION_COOKIE_NAME) is not None
        set_cookie = resp.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()
        # Exact-match, not a substring check: "Path=/" is also a substring of
        # "Path=/rest/v1/orchestrate", which would let a regression to the
        # narrower (browser-unreachable in gateway mode -- see
        # SESSION_COOKIE_PATH's docstring) scope slip past this test.
        attributes = {a.strip().split("=")[0].lower(): a.strip() for a in set_cookie.split(";")}
        assert attributes["path"] == f"Path={SESSION_COOKIE_PATH}"

    def test_secure_flag_follows_explicit_public_https(self, client, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!", enable_https="true")
        conf["public_scheme"] = "https"
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)

        resp = client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})

        assert "secure" in resp.headers["set-cookie"].lower()

    def test_secure_flag_follows_enable_https_false(self, client, monkeypatch):
        """enable_https=false is the shipped default (#10) -- a Secure
        cookie would be silently dropped by the browser over plain HTTP,
        breaking every subsequent authenticated request."""
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!", enable_https="false")
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)

        resp = client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})

        assert "secure" not in resp.headers["set-cookie"].lower()

    def test_response_body_no_longer_carries_the_token(self, client, monkeypatch):
        """httpOnly is meaningless if the very login response still hands
        the token back in a script-readable JSON body."""
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!")
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)

        resp = client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})

        assert "token" not in resp.json()["data"]


class TestLogoutClearsSessionCookie:
    def test_logout_expires_the_cookie(self, client, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!")
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)
        client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})
        assert client.cookies.get(SESSION_COOKIE_NAME) is not None

        resp = client.post(f"{BASE}/auth/logout")

        assert resp.status_code == 200
        set_cookie = resp.headers["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        assert ("Max-Age=0" in set_cookie) or ("01 Jan 1970" in set_cookie)

    def test_logout_revokes_the_underlying_token(self, client, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        conf = _file_mode_conf("MyRealPassword1!")
        monkeypatch.setattr(srv, "get_conf", lambda: conf)
        monkeypatch.setattr(auth_module, "get_conf", lambda: conf)
        client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "MyRealPassword1!"})
        token = client.cookies.get(SESSION_COOKIE_NAME)

        client.post(f"{BASE}/auth/logout")

        assert auth_module.get_session_store().validate(token) is False


class TestCorsCredentialsNeverPairWithWildcard:
    """Regression coverage: Starlette's CORSMiddleware doesn't reject
    allow_origins=["*"] + allow_credentials=True the way a browser rejects a
    literal wildcard on the wire -- it silently echoes back whatever Origin
    the request carries, which would let any origin make a credentialed
    (cookie-carrying) request to the internal API. allow_credentials must
    never be True while the origin allowlist is still the wildcard default.
    """

    def test_cors_middleware_does_not_pair_wildcard_origin_with_credentials(self):
        cors = next(
            m for m in srv.app.user_middleware
            if m.cls.__name__ == "CORSMiddleware"
        )
        if "*" in cors.kwargs["allow_origins"]:
            assert cors.kwargs["allow_credentials"] is False


class TestExtractTokenPrecedence:
    def test_cookie_used_when_present(self):
        response = Response()
        request_scope = {
            "type": "http", "method": "GET", "path": "/x",
            "headers": [(b"cookie", b"session_token=cookie-token")],
            "query_string": b"",
        }
        from fastapi import Request
        assert auth_module.extract_token(Request(request_scope)) == "cookie-token"

    def test_bearer_header_used_as_fallback_for_scripted_clients(self):
        from fastapi import Request
        request_scope = {
            "type": "http", "method": "GET", "path": "/x",
            "headers": [(b"authorization", b"Bearer header-token")],
            "query_string": b"",
        }
        assert auth_module.extract_token(Request(request_scope)) == "header-token"

    def test_query_param_no_longer_honored(self):
        from fastapi import Request
        request_scope = {
            "type": "http", "method": "GET", "path": "/x",
            "headers": [],
            "query_string": b"access_token=leaked-token",
        }
        assert auth_module.extract_token(Request(request_scope)) is None
