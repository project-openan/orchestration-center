# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in live PostgreSQL tests. Each test creates and drops a uniquely named DB.

Set ORCH_POSTGRESQL_TEST_HOST/PORT/USER/PASSWORD for a disposable test server.
Never point these at production. No existing database or local config is used:
``db_config.json`` is bypassed by seeding the connection-info holder directly.

This is the PostgreSQL counterpart of ``test_mysql_integration.py``. It exists
because PostgreSQL is the oldest supported database backend yet had no
live-database coverage at all: every PostgreSQL path was only exercised through
mocks, so schema drift between the two backends stayed invisible.
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from database.utils import db_connection, user_store
from database.utils.query_execution import execute_query
from database.utils.table_creation import create_tables
from orchestrate.core.model.execution_record import ExecutionRecord, ExecutionStatus
from orchestrate.core.model.psop import PSOP
from orchestrate.handlers import execution_record_processor as records
from orchestrate.handlers import psop_processor as psops

pytestmark = pytest.mark.skipif(not os.environ.get("ORCH_POSTGRESQL_TEST_HOST"),
                                reason="Explicit disposable PostgreSQL test server not configured")


def _maintenance_connection(config, database="postgres"):
    """Talk to the maintenance database: used to drop the generated test schema."""
    conn = psycopg2.connect(host=config["host"], port=config["port"], user=config["user"],
                            password=config["password"], database=database, connect_timeout=5)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def _open_connection(attempts=10, delay=2.0):
    """Connect through the product path, waiting out a server that is not serving yet.

    A container healthcheck proves that postgres answers, not that it accepts an
    authenticated handshake: connecting during that window fails, while the same
    call succeeds seconds later. ``create_connection()`` reports either case as
    ``None``, so retry a bounded number of times and only then fail loudly.
    """
    last_attempt = "no attempt was made"
    for attempt in range(max(1, attempts)):
        try:
            conn = db_connection.create_connection()
        except Exception as error:  # pragma: no cover - depends on driver/server state
            conn, last_attempt = None, repr(error)
        if conn is not None:
            return conn
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise AssertionError(f"PostgreSQL was not reachable within the retry budget: {last_attempt}")


@pytest.fixture
def live_postgres(monkeypatch):
    """Point the product code at a throwaway database and drop it afterwards."""
    from common.util import persistence_mode

    database = "oc_test_" + uuid4().hex
    config = {
        "host": os.environ["ORCH_POSTGRESQL_TEST_HOST"],
        "port": int(os.environ.get("ORCH_POSTGRESQL_TEST_PORT", "5432")),
        "user": os.environ.get("ORCH_POSTGRESQL_TEST_USER", "postgres"),
        "password": os.environ.get("ORCH_POSTGRESQL_TEST_PASSWORD", ""),
        "database": database,
        "connect_timeout": 5,
    }
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "postgresql"})
    # Bypass etc/conf/db_config.json entirely: seed the parsed-config cache the
    # connection module reads, and re-arm the one-shot "database exists" check.
    monkeypatch.setattr(db_connection._ConnInfoHolder, "_instance", config)
    monkeypatch.setattr(db_connection, "_database_verified", False)
    monkeypatch.setattr(user_store, "_any_user_exists_cache", False)
    # The fixture itself runs the startup path (create_tables below), so the
    # TESTING gate has to be armed here - before the test body gets a chance -
    # to keep deployment-time default-data seeding out of the throwaway schema.
    monkeypatch.setenv("TESTING", "true")
    try:
        # The product code itself creates the database when it is missing.
        conn = _open_connection()
        conn.close()
        create_tables()
        yield config
    finally:
        # Exact generated test schema only: no names from config or user input.
        assert database.startswith("oc_test_") and len(database) == 40
        keep = _maintenance_connection(config)
        try:
            with keep.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        finally:
            keep.close()


def test_live_default_seeds_are_idempotent_and_preserve_user_edits(live_postgres, monkeypatch):
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


@pytest.mark.parametrize('session_timezone', ['UTC', 'Asia/Shanghai'])
def test_live_crud_unicode_upsert_large_records_and_utc(live_postgres, sample_psop_dict, monkeypatch, session_timezone):
    monkeypatch.setitem(live_postgres, 'options', '-c timezone='+session_timezone)
    create_tables()  # startup is idempotent
    psop = PSOP.model_validate({
        **sample_psop_dict,
        "name": "中文节能🚀",
        # psop.description is VARCHAR(1024) in Postgres but LONGTEXT in MySQL;
        # this stays inside the narrower column on purpose (see the schema probe
        # below, which pins the divergence for the schema-alignment work).
        "description": "中文" * 200,
        "user_intent": "意图" * 2000,
    })
    assert psops.custom_save_psop(psop) == psop.id
    assert psops.get_psop_by_id(psop.id).description == psop.description
    assert psops.get_psop_by_id(psop.id).user_intent == psop.user_intent
    psop.name = "更名的方案🚀"
    psops.custom_save_psop(psop)
    assert len(psops.get_all_psops()) == 1
    assert psops.get_psop_by_id(psop.id).name == psop.name
    # Identifiers are case sensitive and never interpolated as SQL.
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
    conn = db_connection.create_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT started_at FROM execution_records WHERE execution_id=%s', (record.execution_id,))
            assert cursor.fetchone()[0] == datetime(2026, 10, 9, 0, 5)
    finally:
        conn.close()
    assert records.db_delete_execution_record(record.execution_id)
    assert not records.db_delete_execution_record(record.execution_id)
    assert psops.custom_delete_psop(psop.id)
    assert not psops.custom_delete_psop(psop.id)


def test_live_schema_divergence_from_mysql(live_postgres):
    """Pin the two known PostgreSQL/MySQL schema differences (fixed by P2).

    Both probes go through raw SQL so they observe the column type itself, not a
    model-level validation rule.
    """
    conn = db_connection.create_connection()
    try:
        # 1. psop.description: VARCHAR(1024) here, LONGTEXT in MySQL, so a long
        #    description that MySQL accepts is rejected by PostgreSQL.
        _, error = execute_query(
            conn,
            "INSERT INTO psop (id, name, description, psop_content) VALUES (%s, %s, %s, %s)",
            ("probe-long-description", "probe", "x" * 2000, "{}"),
        )
        assert error is not None, "PostgreSQL accepted an over-long description; did the column widen?"
        rows, _ = execute_query(conn, "SELECT 1 FROM psop WHERE id = 'probe-long-description'")
        assert rows == [], "the rejected row must not be partially stored"

        # 2. psop.id: VARCHAR(1024) here, VARCHAR(255) in MySQL. The port contract
        #    caps ids at 255 and validates before storage, so this probe flips
        #    from "accepted" to "rejected" when that cap lands.
        conn.rollback()
        _, error = execute_query(
            conn,
            "INSERT INTO psop (id, name, description, psop_content) VALUES (%s, %s, %s, %s)",
            ("p" * 300, "probe", "probe", "{}"),
        )
        assert error is None, f"PostgreSQL rejected a 300-character id: {error}"
        assert psops.custom_delete_psop("p" * 300)
    finally:
        conn.close()


def test_live_users_legacy_migration_and_failure_rollback(live_postgres):
    # Recreate only this test's users table in its legacy shape.
    conn = db_connection.create_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE users")
            cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, "
                        "username VARCHAR(64) UNIQUE NOT NULL, password_hash VARCHAR(128) NOT NULL, "
                        "salt VARCHAR(64) NOT NULL, role VARCHAR(16) DEFAULT 'user', "
                        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("INSERT INTO users (username, password_hash, salt) VALUES (%s,%s,%s)",
                        ("legacy", user_store._hash_password(user_store.hashlib.sha256(b"LegacyPass9!").hexdigest(), "salt"), "salt"))
        conn.commit()
    finally:
        conn.close()
    create_tables()
    assert user_store.authenticate_user("legacy", "LegacyPass9!")["username"] == "legacy"
    # The successful legacy login must have upgraded the stored scheme in place.
    conn = db_connection.create_connection()
    try:
        rows, error = execute_query(conn, "SELECT password_scheme FROM users WHERE username = %s", ("legacy",))
        assert error is None and rows[0][0] != "legacy"
    finally:
        conn.close()
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
    conn = db_connection.create_connection()
    try:
        _, err = execute_query(conn, "INSERT INTO missing_table VALUES (1)")
        assert err is not None
        conn.rollback()
        rows, err = execute_query(conn, "SELECT 1")
        # psycopg2 returns rows as a list of tuples; pymysql returns a tuple of
        # tuples. Another shape the shared SQL layer will have to make uniform.
        assert rows == [(1,)] and err is None
    finally:
        conn.close()


def test_live_connection_lifecycle_and_close_is_noop(live_postgres):
    """PostgreSQL has no pool: connections are per operation and close is a no-op."""
    first, second = db_connection.create_connection(), db_connection.create_connection()
    try:
        assert first is not None and second is not None
        with first.cursor() as cur:
            cur.execute("INSERT INTO psop (id,name) VALUES ('uncommitted','rollback')")
        first.close()
        # Closing without committing must not leave the row behind.
        assert psops.get_psop_by_id("uncommitted") is None
        # close_database() only releases the MySQL pool; it must stay safe here
        # and must not disturb connections opened afterwards.
        db_connection.close_database()
        after = db_connection.create_connection()
        assert after is not None
        after.close()
    finally:
        try:
            first.close()
        except Exception:
            pass
        try:
            second.close()
        except Exception:
            pass


def test_live_unreachable_database_reports_none(monkeypatch):
    """Pin the current contract: an unreachable database yields None, not an exception.

    The storage-port work turns this into a typed StorageUnavailableError so the
    API can answer 503 instead of "no data"; until then this test documents the
    behaviour that callers actually have to cope with.
    """
    from common.util import persistence_mode

    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "postgresql"})
    monkeypatch.setattr(db_connection._ConnInfoHolder, "_instance", {
        "host": "127.0.0.1", "port": 1, "user": "nobody", "password": "", "database": "oc_test_unreachable",
        "connect_timeout": 2,
    })
    monkeypatch.setattr(db_connection, "_database_verified", False)
    assert db_connection.create_database_if_not_exists() is False
    assert db_connection.create_connection() is None


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
def test_live_http_https_auth_workflow_and_execution_apis(live_postgres, sample_psop_dict, tmp_path, https):
    config = live_postgres
    record = ExecutionRecord(psop_id=sample_psop_dict["id"], psop_name="测试执行", status=ExecutionStatus.SUCCESS)
    records.db_save_execution_record(record)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [sys.executable, str(Path(__file__).with_name("postgres_smoke_server.py")), str(port)]
    if https:
        cert, key = _certificate(tmp_path)
        command.extend([str(cert), str(key)])
    env = {**os.environ, "OC_POSTGRES_SMOKE_CONFIG": json.dumps(config), "PYTHON_DOTENV_DISABLED": "1"}
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
                        pytest.fail("PostgreSQL API server exited before readiness; see service.log")
                    try:
                        response = client.get(base + "/auth/check")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        pytest.fail("PostgreSQL API server readiness timed out")
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
