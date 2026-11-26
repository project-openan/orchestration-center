# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared-session contracts on a transactional SQLite DBAPI dialect harness.

This harness exercises two independent stores/processes and real transactions;
it does not claim PostgreSQL/MySQL driver or isolation-level verification.
"""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

from fastapi import HTTPException, Request
import pytest

from database.utils import user_store
from database.utils.connection_provider import connection_scope
from orchestrate.persistence.errors import StorageUnavailableError
from orchestrate.server import auth
from orchestrate.server.sql_sessions import shared_store


class Cursor:
    def __init__(self, cur):
        self.cur = cur

    def execute(self, sql, params=()):
        sql = (
            sql.replace("%s", "?")
            .replace(" FOR UPDATE", "")
            .replace(" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin", "")
        )
        if sql == "BEGIN":
            # Serialize short transactions in the harness, including across
            # processes. Production uses users-row locks instead.
            sql = "BEGIN IMMEDIATE"
        if sql.startswith("SELECT EXTRACT(EPOCH") or sql == "SELECT UNIX_TIMESTAMP()":
            sql = "SELECT CAST(strftime('%s', 'now') AS INTEGER)"
        self.cur.execute(sql, params)
        return self

    def fetchone(self):
        return self.cur.fetchone()

    def close(self):
        self.cur.close()


class Connection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=10, isolation_level=None)

    def autocommit(self, value):
        pass

    def cursor(self):
        return Cursor(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


class Provider:
    def __init__(self, path, mode="postgresql"):
        self.path = str(path)
        self.mode = mode
        self._lock = threading.RLock()

    def connection(self):
        return Connection(self.path)


@pytest.fixture(params=["postgresql", "mysql"])
def pair(tmp_path, request, monkeypatch):
    path = tmp_path / "auth.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT, "
            "salt TEXT, role TEXT, must_change_password BOOL, password_scheme TEXT)"
        )
    monkeypatch.setattr(auth, "get_conf", lambda: {"access_token_ttl": "60"})
    a, b = Provider(path, request.param), Provider(path, request.param)
    return shared_store(a), shared_store(b), path


def add_user(path, username="alice", password="FirstPassword9!", role="user", pending=False):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO users VALUES (?, ?, '', ?, ?, ?)",
            (username, user_store._hash_password_bcrypt(password), role, pending, user_store._CURRENT_PASSWORD_SCHEME),
        )


def issue(store, username="alice", password="FirstPassword9!"):
    account = store.authenticate(username, password)
    assert account
    return store.create(username, account["role"], credential_snapshot=account["_auth_snapshot"])[0]


def test_other_instance_can_validate_and_revoke_without_plaintext_storage(pair):
    a, b, path = pair
    add_user(path)
    token = issue(a)
    assert b.identity(token).username == "alice"
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT token_hash FROM account_sessions").fetchall()
    assert rows == [(hashlib.sha256(token.encode()).hexdigest(),)]
    assert token not in path.read_bytes().decode("utf8", errors="ignore")
    b.revoke(token)
    assert a.identity(token) is None


def test_password_change_fences_inflight_login_and_existing_sessions(pair):
    a, b, path = pair
    add_user(path)
    token = issue(a)
    verified_old = a.authenticate("alice", "FirstPassword9!")
    b.update_password("alice", "SecondPassword9!")
    with pytest.raises(HTTPException) as exc:
        a.create("alice", "user", credential_snapshot=verified_old["_auth_snapshot"])
    assert exc.value.status_code == 401
    assert a.identity(token) is None
    assert b.authenticate("alice", "FirstPassword9!") is None
    assert a.authenticate("alice", "SecondPassword9!")


def test_concurrent_self_password_updates_cannot_overwrite_fresher_credentials(pair):
    a, b, path = pair
    add_user(path)
    old = a.authenticate("alice", "FirstPassword9!")["_auth_snapshot"]
    b.update_password("alice", "WinningPassword9!", expected_snapshot=old)
    with pytest.raises(HTTPException) as exc:
        a.update_password("alice", "LosingPassword9!", expected_snapshot=old)
    assert exc.value.status_code == 409
    assert a.authenticate("alice", "WinningPassword9!")
    assert a.authenticate("alice", "LosingPassword9!") is None


def test_delete_recreate_changes_subject_even_when_password_is_identical(pair):
    a, b, path = pair
    add_user(path)
    token = issue(a)
    old = a.identity(token)
    assert b.subject_authorized(old.subject_id, "user")
    b.delete_account("alice")
    add_user(path)
    token2 = issue(b)
    assert a.identity(token) is None
    assert a.identity(token2).subject_id != old.subject_id
    assert not a.subject_authorized(old.subject_id, "user")


def test_forced_change_is_shared_and_enforced_at_authorization(pair, monkeypatch):
    a, b, path = pair
    add_user(path, pending=True)
    token = issue(a)
    monkeypatch.setattr(auth, "get_session_store", lambda: b)
    request = Request({"type": "http", "headers": [(b"authorization", ("Bearer " + token).encode())]})
    with pytest.raises(HTTPException) as exc:
        auth.require_session_identity(request)
    assert exc.value.status_code == 403
    identity = auth.require_session_identity(request, allow_password_change=True)
    assert identity.must_change_password
    assert not b.subject_authorized(identity.subject_id, identity.role)
    assert b.change_password("alice", "FirstPassword9!", "SecondPassword9!")
    assert a.identity(token) is None
    new_token = issue(a, password="SecondPassword9!")
    assert not b.identity(new_token).must_change_password


def test_role_reduction_invalidates_old_role_and_queued_dispatch(pair):
    a, b, path = pair
    add_user(path, role="admin")
    token = issue(a)
    subject = a.identity(token).subject_id
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE users SET role='user' WHERE username='alice'")
    assert b.identity(token) is None
    assert not b.subject_authorized(subject, "admin")
    assert b.subject_authorized(subject, "user")


def test_legacy_mutation_entries_use_shared_authority(pair):
    a, b, path = pair
    add_user(path)
    token = issue(a)
    with connection_scope(b.provider):
        assert user_store.update_password("alice", "SecondPassword9!")
    assert a.identity(token) is None
    token = issue(a, password="SecondPassword9!")
    with connection_scope(b.provider):
        assert user_store.delete_user("alice")
    assert a.identity(token) is None


def test_session_expiry_and_store_failure_fail_closed(pair, monkeypatch):
    a, b, path = pair
    add_user(path)
    token = issue(a)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE account_sessions SET expires_at=0")
    assert b.identity(token) is None

    def unavailable():
        raise ConnectionError("synthetic outage")

    monkeypatch.setattr(a.provider, "connection", unavailable)
    with pytest.raises(StorageUnavailableError):
        a.identity(token)


def test_session_can_be_validated_by_a_fresh_python_process(pair):
    a, _, path = pair
    add_user(path)
    token = issue(a)
    source = Path(__file__).resolve()
    script = (
        "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
        "s=m['shared_store'](m['Provider'](sys.argv[2],sys.argv[3])); "
        "assert s.identity(sys.stdin.read()).username=='alice'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(path), a.provider.mode],
        input=token,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
