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

import hashlib

import bcrypt
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.responses import Response

os.environ.setdefault("TESTING", "True")

from orchestrate.server import frontend_support_server as srv


def _http_request(token=None):
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": headers, "query_string": b""}
    return Request(scope)


@pytest.mark.anyio
class TestLoginFileMode:
    """Regression coverage for #9a: frontend no longer pre-hashes; the
    backend now hashes the plaintext it receives before comparing."""

    async def test_correct_plaintext_password_succeeds(self, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        stored_hash = hashlib.sha256(b"MyRealPassword1!").hexdigest()
        monkeypatch.setattr(srv, "get_conf", lambda: {
            "persistence_mode": "file", "access_password": stored_hash,
        })
        response = Response()
        result = await srv.login(srv.LoginRequest(username="admin", password="MyRealPassword1!"), response)
        assert result["data"]["auth_required"] is True
        assert "session_token=" in response.headers["set-cookie"]

    async def test_wrong_plaintext_password_rejected(self, monkeypatch):
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        stored_hash = hashlib.sha256(b"MyRealPassword1!").hexdigest()
        monkeypatch.setattr(srv, "get_conf", lambda: {
            "persistence_mode": "file", "access_password": stored_hash,
        })
        with pytest.raises(HTTPException) as exc_info:
            await srv.login(srv.LoginRequest(username="admin", password="wrong-password"), Response())
        assert exc_info.value.status_code == 401

    async def test_previously_client_hashed_value_no_longer_works(self, monkeypatch):
        """The old client-side sha256(password) digest must NOT authenticate
        anymore -- that was exactly the pass-the-hash surface #9 closes."""
        monkeypatch.setattr(srv, "is_auth_enabled", lambda: True)
        stored_hash = hashlib.sha256(b"MyRealPassword1!").hexdigest()
        monkeypatch.setattr(srv, "get_conf", lambda: {
            "persistence_mode": "file", "access_password": stored_hash,
        })
        old_client_hash = hashlib.sha256(b"MyRealPassword1!").hexdigest()
        with pytest.raises(HTTPException) as exc_info:
            await srv.login(srv.LoginRequest(username="admin", password=old_client_hash), Response())
        assert exc_info.value.status_code == 401


@pytest.mark.anyio
class TestRegisterComplexity:
    async def test_rejects_password_with_single_character_type(self, monkeypatch):
        monkeypatch.setattr(srv, "get_conf", lambda: {
            "persistence_mode": "postgresql", "auth.register.enabled": "true"})
        with pytest.raises(HTTPException) as exc_info:
            await srv.register(srv.RegisterRequest(username="alice", password="aaaaaaaa"))
        assert exc_info.value.status_code == 400
        assert "complexity" in exc_info.value.detail.lower()

    async def test_accepts_password_meeting_complexity(self, monkeypatch):
        monkeypatch.setattr(srv, "get_conf", lambda: {
            "persistence_mode": "postgresql", "auth.register.enabled": "true"})
        with patch("database.utils.user_store.user_exists", return_value=False), \
             patch("database.utils.user_store.create_user", return_value=True) as mock_create:
            result = await srv.register(srv.RegisterRequest(username="alice", password="Str0ngPass"))
            assert result["data"]["username"] == "alice"
            mock_create.assert_called_once_with("alice", "Str0ngPass")

    def test_too_short_password_rejected_at_the_model_layer(self):
        with pytest.raises(ValidationError):
            srv.RegisterRequest(username="alice", password="Ab1")


@pytest.mark.anyio
class TestChangePasswordDbMode:
    async def test_rejects_weak_new_password(self, monkeypatch):
        monkeypatch.setattr(srv, "get_conf", lambda: {"persistence_mode": "postgresql"})
        store = srv.get_session_store()
        token, _ = store.create("alice")
        try:
            request = srv.ChangePasswordRequest(old_password="OldPassw0rd!", new_password="aaaaaaaa")
            with pytest.raises(HTTPException) as exc_info:
                await srv.change_password(request, _http_request(token))
            assert exc_info.value.status_code == 400
        finally:
            store.revoke(token)

    async def test_accepts_strong_new_password(self, monkeypatch):
        monkeypatch.setattr(srv, "get_conf", lambda: {"persistence_mode": "postgresql"})
        store = srv.get_session_store()
        token, _ = store.create("alice")
        try:
            request = srv.ChangePasswordRequest(old_password="OldPassw0rd!", new_password="NewStr0ngPass!")
            with patch("database.utils.user_store.authenticate_user", return_value={"username": "alice", "role": "user"}), \
                 patch("database.utils.user_store.update_password", return_value=True) as mock_update:
                result = await srv.change_password(request, _http_request(token))
                assert result["message"] == "Password changed successfully"
                mock_update.assert_called_once_with("alice", "NewStr0ngPass!")
        finally:
            store.revoke(token)


@pytest.mark.anyio
class TestChangePasswordFileMode:
    async def test_hashes_old_and_new_password_before_comparing_and_storing(self, monkeypatch, tmp_path):
        old_hash = hashlib.sha256(b"OldPassw0rd!").hexdigest()
        conf_path = tmp_path / "server.conf"
        conf_path.write_text(f"access_password={old_hash}\n", encoding="utf-8")

        monkeypatch.setattr(srv, "get_conf", lambda: {"persistence_mode": "file", "access_password": old_hash})
        monkeypatch.setattr(srv.get_conf, "cache_clear", lambda: None, raising=False)

        real_join = os.path.join

        def _fake_join(*parts):
            if parts[-3:] == ("etc", "conf", "server.conf"):
                return str(conf_path)
            return real_join(*parts)

        store = srv.get_session_store()
        token, _ = store.create("admin")
        try:
            request = srv.ChangePasswordRequest(old_password="OldPassw0rd!", new_password="NewPassw0rd!")
            with patch.object(srv.os.path, "join", side_effect=_fake_join):
                result = await srv.change_password(request, _http_request(token))
            assert result["message"] == "Password changed successfully"
            written = conf_path.read_text(encoding="utf-8")
            # 改密后存的是带版本标记的 bcrypt 哈希,且能用新口令验证通过
            assert written.startswith("access_password=v4:$2")
            stored_hash = written.split("=", 1)[1].strip()
            assert srv._verify_access_password(stored_hash, "NewPassw0rd!")
        finally:
            store.revoke(token)

    async def test_wrong_old_password_rejected(self, monkeypatch, tmp_path):
        old_hash = hashlib.sha256(b"OldPassw0rd!").hexdigest()
        monkeypatch.setattr(srv, "get_conf", lambda: {"persistence_mode": "file", "access_password": old_hash})

        store = srv.get_session_store()
        token, _ = store.create("admin")
        try:
            request = srv.ChangePasswordRequest(old_password="wrong", new_password="NewPassw0rd!")
            with pytest.raises(HTTPException) as exc_info:
                await srv.change_password(request, _http_request(token))
            assert exc_info.value.status_code == 401
        finally:
            store.revoke(token)
