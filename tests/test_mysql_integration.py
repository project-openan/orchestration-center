# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in live MySQL tests. Each test creates and drops a uniquely named DB.

Set ORCH_MYSQL_TEST_HOST/PORT/USER/PASSWORD for a disposable test server.
Never point these at production. No existing database or local config is used.
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pymysql
import pytest

from database.utils import mysql_connection, user_store
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.execution_record import ExecutionRecord, ExecutionStatus
from orchestrate.handlers import psop_processor as psops
from orchestrate.handlers import execution_record_processor as records

pytestmark = pytest.mark.skipif(not os.environ.get("ORCH_MYSQL_TEST_HOST"),
                                reason="Explicit disposable MySQL test server not configured")


def _open_backend(attempts: int = 10, delay: float = 2.0):
    """Open the MySQL backend, waiting out a server that is not serving yet.

    A container healthcheck proves that mysqld answers, not that it accepts an
    authenticated handshake: connecting during that window fails inside the
    driver, while the same call succeeds seconds later. Retry a bounded number
    of times so the suite reports the real error instead of flaking, and always
    release a half-built backend before trying again.
    """
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            return mysql_connection.get_backend()
        except Exception as error:
            last_error = error
            mysql_connection.close_backend()
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise last_error


@pytest.fixture
def live_mysql(monkeypatch):
    from common.util import persistence_mode
    database = "oc_test_" + uuid4().hex
    config = {
        "host": os.environ["ORCH_MYSQL_TEST_HOST"],
        "port": int(os.environ.get("ORCH_MYSQL_TEST_PORT", "3306")),
        "user": os.environ.get("ORCH_MYSQL_TEST_USER", "root"),
        "password": os.environ.get("ORCH_MYSQL_TEST_PASSWORD", ""),
        "database": database, "pool_min": 1, "pool_max": 2,
        "connect_timeout": 5, "read_timeout": 5, "write_timeout": 5,
    }
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "mysql"})
    monkeypatch.setattr(mysql_connection, "load_mysql_config", lambda: config)
    monkeypatch.setattr(mysql_connection, "_backend", None)
    monkeypatch.setattr(user_store, "_any_user_exists_cache", False)
    try:
        backend = _open_backend()
        backend.create_tables()
        yield config, backend
    finally:
        mysql_connection.close_backend()
        # Exact generated test schema only: no names from config/user input.
        assert database.startswith("oc_test_") and len(database) == 40
        conn = pymysql.connect(host=config["host"], port=config["port"], user=config["user"],
                               password=config["password"], autocommit=True, ssl_disabled=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            conn.close()


def test_live_crud_unicode_upsert_large_records_and_utc(live_mysql, sample_psop_dict):
    _, backend = live_mysql
    backend.create_tables()  # startup is idempotent
    psop = PSOP.model_validate({**sample_psop_dict, "name": "中文节能🚀", "description": "中文" * 40000})
    assert psops.custom_save_psop(psop) == psop.id
    assert psops.get_psop_by_id(psop.id).description == psop.description
    psop.name = "更新的方案🚀"
    psops.custom_save_psop(psop)
    assert len(psops.get_all_psops()) == 1
    assert psops.get_psop_by_id(psop.id).name == psop.name
    assert psops.get_psop_by_id(psop.id.upper()) is None
    assert psops.get_psop_by_id("x' OR 1=1 --") is None
    record = ExecutionRecord(psop_id=psop.id, psop_name=psop.name,
        started_at=datetime(2026, 10, 9, 8, 5, tzinfo=timezone(timedelta(hours=8))),
        events=[{"payload": "通知🚀" * 40000}])
    records.db_save_execution_record(record)
    record.status = ExecutionStatus.SUCCESS
    record.completed_at = datetime(2026, 10, 9, 8, 6, tzinfo=timezone(timedelta(hours=8)))
    records.db_save_execution_record(record)
    assert records.db_get_execution_record(record.execution_id) == record
    summaries = records.db_list_execution_records()
    assert len(summaries) == 1 and summaries[0]["status"] == "success"
    assert summaries[0]["started_at"] == "2026-10-09T00:05:00+00:00"
    assert summaries[0]["completed_at"] == "2026-10-09T00:06:00+00:00"
    assert records.db_delete_execution_record(record.execution_id)
    assert not records.db_delete_execution_record(record.execution_id)
    assert psops.custom_delete_psop(psop.id)
    assert not psops.custom_delete_psop(psop.id)


def test_live_default_seeds_are_idempotent_and_preserve_user_edits(live_mysql, monkeypatch):
    from database.utils.seed_data import seed_default_psops
    monkeypatch.delenv('TESTING', raising=False)
    assert seed_default_psops() == 19
    from database.utils.seed_data import SEED_DATA_DIR
    for path in SEED_DATA_DIR.glob('*.json'):
        expected = PSOP.model_validate_json(path.read_text(encoding='utf-8'))
        assert psops.get_psop_by_id(expected.id) == expected
    workflow = psops.get_psop_by_id(psops.get_all_psops()[0].workflow_id)
    workflow.name = 'Operator edited default'
    psops.custom_save_psop(workflow)
    assert seed_default_psops() == 0
    assert psops.get_psop_by_id(workflow.id).name == 'Operator edited default'
    assert len(psops.get_all_psops()) == 19


def test_live_users_legacy_migration_and_failure_rollback(live_mysql):
    from database.utils.query_execution import execute_query
    _, backend = live_mysql
    # Recreate only this test's users table in its legacy shape.
    conn = backend.connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE users")
            cur.execute("CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, "
                        "username VARCHAR(64) UNIQUE NOT NULL, password_hash VARCHAR(128) NOT NULL, "
                        "salt VARCHAR(64) NOT NULL, role VARCHAR(16) DEFAULT 'user', "
                        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB")
            cur.execute("INSERT INTO users (username, password_hash, salt) VALUES (%s,%s,%s)",
                        ("legacy", user_store._hash_password(user_store.hashlib.sha256(b"LegacyPass9!").hexdigest(), "salt"), "salt"))
        conn.commit()
    finally:
        conn.close()
    backend.create_tables()
    assert user_store.authenticate_user("legacy", "LegacyPass9!")["username"] == "legacy"
    assert user_store.seed_admin_if_empty() is False
    assert user_store.create_user("Alice", "UserPass9!")
    assert user_store.authenticate_user("Alice", "wrong") is None
    assert user_store.authenticate_user("alice", "UserPass9!") is None
    assert user_store.authenticate_user("Alice", "UserPass9!")["role"] == "user"
    assert not user_store.create_user("Alice", "Duplicate9!")
    assert user_store.update_password("Alice", "ChangedPass9!")
    assert user_store.authenticate_user("Alice", "ChangedPass9!")
    assert user_store.delete_user("Alice")
    assert not user_store.user_exists("Alice")
    conn = backend.connection()
    try:
        _, err = execute_query(conn, "INSERT INTO missing_table VALUES (1)")
        assert err is not None
        rows, err = execute_query(conn, "SELECT 1")
        assert rows == ((1,),) and err is None
    finally:
        conn.close()


def test_live_pool_exhaustion_and_close_reset(live_mysql):
    _, backend = live_mysql
    from dbutils.pooled_db import TooManyConnections
    first, second = backend.connection(), backend.connection()
    try:
        with pytest.raises(TooManyConnections):
            backend.connection()
        with first.cursor() as cur:
            cur.execute("INSERT INTO psop (id,name) VALUES ('uncommitted','rollback')")
        first.close()
        assert psops.get_psop_by_id("uncommitted") is None
    finally:
        first.close()
        second.close()


def _certificate(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import ipaddress
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "server.pem", tmp_path / "server.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert_path, key_path


@pytest.mark.parametrize("https", [False, True])
def test_live_http_https_auth_workflow_and_execution_apis(live_mysql, sample_psop_dict, tmp_path, https):
    config, _ = live_mysql
    record = ExecutionRecord(psop_id=sample_psop_dict["id"], psop_name="测试执行", status=ExecutionStatus.SUCCESS)
    records.db_save_execution_record(record)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [sys.executable, str(Path(__file__).with_name("mysql_smoke_server.py")), str(port)]
    if https:
        cert, key = _certificate(tmp_path)
        command.extend([str(cert), str(key)])
    env = {**os.environ, "OC_MYSQL_SMOKE_CONFIG": json.dumps(config), "PYTHON_DOTENV_DISABLED": "1"}
    env.pop("TESTING", None)
    base = f"{'https' if https else 'http'}://127.0.0.1:{port}/rest/v1/orchestrate"
    log_path = tmp_path / "service.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=env,
                                   cwd=Path(__file__).resolve().parents[1])
        try:
            with httpx.Client(verify=False, timeout=10) as client:
                deadline = time.monotonic() + 45
                while True:
                    if process.poll() is not None:
                        pytest.fail("MySQL API server exited before readiness; see service.log")
                    try:
                        response = client.get(base + "/auth/check")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        pytest.fail("MySQL API server readiness timed out")
                    time.sleep(0.2)
                assert response.json()["data"]["auth_required"] is True
                assert client.get(base + "/workflows").status_code == 401
                assert client.post(base + "/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
                login = client.post(base + "/auth/login", json={"username": "admin", "password": "SmokeAdmin9!"})
                assert login.status_code == 200 and login.json()["data"]["must_change_password"] is True
                changed = client.post(base + "/auth/change-password", json={"old_password": "SmokeAdmin9!", "new_password": "ChangedAdmin9!"})
                assert changed.status_code == 200
                assert client.get(base + "/workflows").status_code == 401
                assert client.post(base + "/auth/login", json={"username": "admin", "password": "ChangedAdmin9!"}).status_code == 200
                public_base = base.removesuffix("/rest/v1/orchestrate") + "/api/v1"
                issued = client.post(public_base + "/auth/token", json={"username": "admin", "password": "ChangedAdmin9!"})
                assert issued.status_code == 200, issued.text
                bearer = {"Authorization": "Bearer " + issued.json()["access_token"]}
                saved = client.post(base + "/workflows", json={"psop": sample_psop_dict})
                assert saved.status_code == 201
                psop_id = saved.json()["data"]["workflow_id"]
                assert client.get(base + f"/workflows/{psop_id}").json()["data"]["id"] == psop_id
                assert client.get(public_base + f"/orchestrate/psop/{psop_id}").status_code == 401
                assert client.get(public_base + f"/orchestrate/psop/{psop_id}", headers=bearer).json()["data"]["id"] == psop_id
                assert client.post(public_base + "/auth/logout", headers=bearer).status_code == 200
                assert client.get(public_base + f"/orchestrate/psop/{psop_id}", headers=bearer).status_code == 401
                assert any(row["workflow_id"] == psop_id for row in client.get(base + "/workflows").json()["data"])
                # POST uses the same upsert handler when editing an existing workflow.
                updated = {**sample_psop_dict, "name": "更新工作流"}
                assert client.post(base + "/workflows", json={"psop": updated}).status_code == 201
                assert client.get(base + f"/workflows/{psop_id}").json()["data"]["name"] == "更新工作流"
                assert client.get(base + "/execution-records").status_code == 200
                assert client.get(base + f"/execution-records/{record.execution_id}").status_code == 200
                assert client.delete(base + f"/execution-records/{record.execution_id}").status_code == 200
                assert client.get(base + f"/execution-records/{record.execution_id}").status_code == 404
                assert client.delete(base + f"/workflows/{psop_id}").status_code == 200
                assert client.get(base + f"/workflows/{psop_id}").status_code == 404
                registered = client.post(base + "/auth/register", json={"username": "smoke_user", "password": "NewUserPass9!"})
                assert registered.status_code == 200 and registered.json()["code"] == 201
                assert client.get(base + "/auth/users").status_code == 200
                assert client.delete(base + "/auth/users/smoke_user").status_code == 200
                assert client.post(base + "/auth/logout").status_code == 200
                assert client.get(base + "/workflows").status_code == 401
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
