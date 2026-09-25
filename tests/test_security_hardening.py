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

# tests/test_security_hardening.py
import os
import subprocess
import sys
import threading

import anyio
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from orchestrate.server.frontend_support_server import app
from orchestrate.server.auth import get_session_store
from orchestrate.core.persistence import WorkflowStorage, WorkflowStorageError


@pytest.fixture
def client(_testing_mode):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _testing_mode(monkeypatch):
    monkeypatch.setenv("TESTING", "True")


@pytest.fixture(autouse=True)
def _no_login_rate_limit():
    """登录测试不走真实限流(共享的 5 次/分钟/IP 预算会被本文件的多个
    登录用例消耗,导致后续测试 429)。本文件内限流全部放行。"""
    with patch("orchestrate.server.middleware.async_hit", return_value=True):
        yield


# ---------------------------------------------------------------------------
# 1. execution_id 校验(路径穿越防护)
# ---------------------------------------------------------------------------

def test_execution_record_rejects_traversal_id(tmp_path):
    storage = WorkflowStorage(storage_dir=str(tmp_path))
    with pytest.raises(WorkflowStorageError):
        storage.load_execution_record("../evil")
    with pytest.raises(WorkflowStorageError):
        storage.delete_execution_record("..\\..\\common\\config\\llm_config")
    with pytest.raises(WorkflowStorageError):
        storage.load_execution_record("ok-id\n")  # re.match + $ 会被换行绕过


def test_execution_record_accepts_normal_id(tmp_path):
    storage = WorkflowStorage(storage_dir=str(tmp_path))
    # 正常 ID 不抛 WorkflowStorageError(不存在时返回 None/False)
    assert storage.load_execution_record("abc-123") is None
    assert storage.delete_execution_record("abc-123") is False


def test_execution_record_delete_endpoint_rejects_bad_id(client):
    resp = client.delete("/rest/v1/orchestrate/execution-records/..%5C..%5Cevil")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. /psops legacy 别名纳入认证
# ---------------------------------------------------------------------------

def test_psops_requires_token_when_auth_enabled(client):
    with patch("orchestrate.server.auth.is_auth_enabled", return_value=True):
        resp = client.get("/psops")
        assert resp.status_code == 401
        resp = client.delete("/psops/some-id")
        assert resp.status_code == 401


def test_psops_allows_valid_session_when_auth_enabled(client):
    token, _ = get_session_store().create("u1", "user")
    with patch("orchestrate.server.auth.is_auth_enabled", return_value=True), \
         patch("orchestrate.server.shared_handlers.SharedHandlers.retrieval") as retrieval:
        retrieval.return_value.list_recent_workflows.return_value = []
        resp = client.get("/psops", cookies={"session_token": token})
        assert resp.status_code == 200


def test_psops_open_when_auth_disabled(client):
    # TESTING=True 时 is_auth_enabled 为 False,与既有行为一致
    with patch("orchestrate.server.shared_handlers.SharedHandlers.retrieval") as retrieval:
        retrieval.return_value.list_recent_workflows.return_value = []
        resp = client.get("/psops")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. 注册开关(默认关闭)
# ---------------------------------------------------------------------------

def test_register_disabled_by_default(client):
    with patch("orchestrate.server.frontend_support_server.get_conf", return_value={}):
        resp = client.post("/rest/v1/orchestrate/auth/register", json={"username": "bob", "password": "Str0ng!pass"})
        assert resp.status_code == 403
        assert "disabled" in resp.json()["message"]


def test_auth_check_matches_registration_gate(client):
    conf = {"persistence_mode": "postgresql"}
    with patch("orchestrate.server.frontend_support_server.get_conf", return_value=conf):
        assert client.get("/rest/v1/orchestrate/auth/check").json()["data"]["registration_enabled"] is False
        conf["auth.register.enabled"] = "true"
        assert client.get("/rest/v1/orchestrate/auth/check").json()["data"]["registration_enabled"] is True


def test_register_works_when_enabled(client, monkeypatch):
    conf = {"auth.register.enabled": "true", "persistence_mode": "postgresql"}
    monkeypatch.setattr("orchestrate.server.frontend_support_server.get_conf", lambda: conf)
    monkeypatch.setattr("database.utils.user_store.user_exists", lambda username: False)
    monkeypatch.setattr("database.utils.user_store.create_user", lambda *a, **k: True)
    resp = client.post("/rest/v1/orchestrate/auth/register", json={"username": "bob", "password": "Str0ng!pass"})
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "bob"


# ---------------------------------------------------------------------------
# 4. DB 不可达时认证 fail-closed(503,而不是放行)
# ---------------------------------------------------------------------------

def test_has_any_user_raises_when_db_unreachable(monkeypatch):
    import database.utils.user_store as user_store
    monkeypatch.setattr(user_store, "_any_user_exists_cache", False)
    monkeypatch.setattr(user_store, "create_connection", lambda: None)
    with pytest.raises(RuntimeError, match="User store unavailable"):
        user_store.has_any_user()


def test_middleware_returns_503_when_user_store_unreachable(client, monkeypatch):
    import database.utils.user_store as user_store
    monkeypatch.setattr(user_store, "_any_user_exists_cache", False)
    monkeypatch.setattr(user_store, "create_connection", lambda: None)

    # 绕过 TESTING 短路,直接模拟 DB 不可达(has_any_user 抛 RuntimeError)
    import orchestrate.server.auth as auth

    def _raise_down():
        raise RuntimeError("User store unavailable: cannot connect to the database")

    monkeypatch.setattr(auth, "is_auth_enabled", _raise_down)

    resp = client.get("/rest/v1/orchestrate/workflows")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 5. 口令哈希:bcrypt(v4)+ 透明迁移
# ---------------------------------------------------------------------------

def test_bcrypt_hash_roundtrip():
    from database.utils.user_store import _hash_password_bcrypt, _verify_password
    stored = _hash_password_bcrypt("S3cret!")
    assert stored.startswith("$2")
    assert _verify_password(stored, "", "v4", "S3cret!")
    assert not _verify_password(stored, "", "v4", "wrong")


def test_legacy_and_v2_schemes_still_verify():
    import hashlib
    from database.utils.user_store import _hash_password, _verify_password
    salt = "abcd"
    # v2
    v2_hash = _hash_password("pw", salt)
    assert _verify_password(v2_hash, salt, "v2", "pw")
    assert not _verify_password(v2_hash, salt, "v2", "other")
    # legacy:存的是 sha256(plaintext) 再加盐哈希
    legacy_hash = _hash_password(hashlib.sha256("pw".encode()).hexdigest(), salt)
    assert _verify_password(legacy_hash, salt, "legacy", "pw")


def test_file_mode_access_password_bcrypt_and_legacy(client, monkeypatch):
    import bcrypt
    from orchestrate.server.frontend_support_server import _hash_access_password, _verify_access_password
    bcrypt_hash = bcrypt.hashpw("adminpw".encode(), bcrypt.gensalt()).decode()
    assert _verify_access_password(bcrypt_hash, "adminpw")
    assert not _verify_access_password(bcrypt_hash, "nope")
    legacy = __import__("hashlib").sha256("adminpw".encode()).hexdigest()
    assert _verify_access_password(legacy, "adminpw")
    long_password = "密" * 40
    versioned_hash = _hash_access_password(long_password)
    assert _verify_access_password(versioned_hash, long_password)
    assert not _verify_access_password(versioned_hash, "密" * 39 + "别")

    # file-mode 登录:TESTING 短路会跳过口令校验,需 patch 端点侧的
    # is_auth_enabled=True 才能走到口令比对分支
    monkeypatch.setattr("orchestrate.server.frontend_support_server.is_auth_enabled", lambda: True)
    monkeypatch.setattr(
        "orchestrate.server.frontend_support_server.get_conf",
        lambda: {"access_password": bcrypt_hash, "enable_https": "false"},
    )
    resp = client.post("/rest/v1/orchestrate/auth/login",
                       json={"username": "admin", "password": "adminpw"})
    assert resp.status_code == 200


    resp = client.post("/rest/v1/orchestrate/auth/login",
                       json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401

    # legacy sha256 存量口令同样可登录
    legacy = __import__("hashlib").sha256("adminpw".encode()).hexdigest()
    monkeypatch.setattr(
        "orchestrate.server.frontend_support_server.get_conf",
        lambda: {"access_password": legacy, "enable_https": "false"},
    )
    resp = client.post("/rest/v1/orchestrate/auth/login",
                       json={"username": "admin", "password": "adminpw"})
    assert resp.status_code == 200


def test_import_does_not_set_testing_for_other_test_modules():
    env = os.environ.copy()
    env.pop("TESTING", None)
    script = (
        "import importlib.util, os; "
        f"spec = importlib.util.spec_from_file_location('isolated_security_tests', {__file__!r}); "
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        "assert 'TESTING' not in os.environ"
    )
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.anyio
async def test_cancelled_retrieval_keeps_slot_until_worker_finishes(monkeypatch):
    from orchestrate.server import frontend_support_server as srv

    started = threading.Event()
    release = threading.Event()
    semaphore = anyio.Semaphore(1)
    monkeypatch.setattr(srv, "retrieve_semaphore", semaphore)

    class SlowRetrieval:
        def retrieve_psop_by_intent(self, _intent):
            started.set()
            release.wait(timeout=5)
            return None

    monkeypatch.setattr(srv.SharedHandlers, "retrieval", lambda: SlowRetrieval())
    scopes = []

    async def request():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await srv.retrieve_by_intent(srv.RetrieveIntentRequest(user_intent="test"))

    try:
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            with anyio.fail_after(2):
                while not started.is_set():
                    await anyio.sleep(0.01)
            scopes[0].cancel()
            await anyio.sleep(0.02)
            with pytest.raises(anyio.WouldBlock):
                semaphore.acquire_nowait()
            release.set()
    finally:
        release.set()
    semaphore.acquire_nowait()
    semaphore.release()
