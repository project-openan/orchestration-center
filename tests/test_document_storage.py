# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Storage contract and failure-interleaving tests; optional real SQL backends."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from orchestrate.persistence.documents import FileDocuments, SqlDocuments
from orchestrate.persistence.errors import StorageConflictError, StorageUnavailableError


@pytest.fixture(params=["file", "mysql", "postgresql"])
def documents(request, tmp_path):
    mode = request.param
    if mode == "file":
        yield FileDocuments(tmp_path)
        return
    prefix = "ORCH_MYSQL_TEST_" if mode == "mysql" else "ORCH_POSTGRESQL_TEST_"
    if not os.environ.get(prefix + "HOST"):
        pytest.skip("Real SQL integration is opt-in")
    from database.utils.connection_provider import SqlConnectionProvider

    database = "orch_storage_" + uuid4().hex[:16]
    config = dict(
        host=os.environ[prefix + "HOST"],
        user=os.environ.get(prefix + "USER", "root" if mode == "mysql" else "postgres"),
        password=os.environ.get(prefix + "PASSWORD", ""),
        port=int(os.environ.get(prefix + "PORT", 3306 if mode == "mysql" else 5432)),
        database=database,
    )
    provider = SqlConnectionProvider(mode, config)
    store = SqlDocuments(provider)
    store.initialize()
    try:
        yield store
    finally:
        provider.close()
        if mode == "mysql":
            import pymysql

            conn = pymysql.connect(**{k: v for k, v in config.items() if k != "database"}, autocommit=True)
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE `{database}`")
        else:
            import psycopg2

            conn = psycopg2.connect(**{**config, "database": "postgres"})
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        conn.close()


def test_transaction_rolls_back_both_documents(documents):
    with pytest.raises(ValueError):
        with documents.transaction():
            documents.save("solution_packages", "pkg", {"id": "pkg"})
            documents.save("sandbox_templates", "workflow", {"id": "workflow"})
            raise ValueError("link failed")
    assert documents.get("solution_packages", "pkg") is None
    assert documents.get("sandbox_templates", "workflow") is None


def test_two_clients_observe_commits_and_revision_conflicts(documents):
    second = FileDocuments(documents.root) if isinstance(documents, FileDocuments) else SqlDocuments(documents.provider)
    revision = documents.save("preflows", "one", {"id": "one"}, expected_revision=0)
    assert second.get("preflows", "one") == {"id": "one"}
    second.save("preflows", "one", {"id": "new"}, expected_revision=revision)
    with pytest.raises(StorageConflictError):
        documents.save("preflows", "one", {"id": "lost"}, expected_revision=revision)
    assert documents.get("preflows", "one")["id"] == "new"


def test_transaction_gate_prevents_read_modify_write_lost_updates(documents):
    documents.save("counter", "one", {"n": 0})

    def increment(_):
        with documents.transaction():
            value = documents.get("counter", "one")
            value["n"] += 1
            documents.save("counter", "one", value)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(20)))
    assert documents.get("counter", "one") == {"n": 20}


def test_caught_nested_failure_marks_entire_uow_for_rollback(documents):
    with pytest.raises(StorageUnavailableError):
        with documents.transaction():
            documents.save("counter", "one", {"n": 1})
            try:
                with documents.transaction():
                    raise ValueError("nested failure")
            except ValueError:
                pass
    assert documents.get("counter", "one") is None


def test_file_partial_replacement_is_recovered_before_any_read(tmp_path, monkeypatch):
    import orchestrate.persistence.documents as module

    store = FileDocuments(tmp_path)
    original = module._atomic
    failed = False

    def fault(path, text):
        nonlocal failed
        if str(path).endswith("b.json") and not failed:
            failed = True
            raise OSError("simulated disk failure after a was published")
        return original(path, text)

    monkeypatch.setattr(module, "_atomic", fault)
    with pytest.raises(StorageUnavailableError):
        with store.transaction():
            store.save("counter", "a", {"n": 1})
            store.save("counter", "b", {"n": 2})
    # Same process, no restart: first read must roll forward b, not expose half-state.
    assert store.get("counter", "a") == {"n": 1}
    assert store.get("counter", "b") == {"n": 2}
    assert not store._state.journal.exists()


def test_sql_legacy_commit_is_owned_by_outer_transaction(documents):
    if isinstance(documents, FileDocuments):
        pytest.skip("SQL transaction ownership contract")
    from database.utils.db_connection import create_connection

    with pytest.raises(ValueError):
        with documents.transaction():
            borrowed = create_connection()
            documents.save("counter", "one", {"n": 1})
            borrowed.commit()
            borrowed.close()
            raise ValueError("outer command fails")
    assert documents.get("counter", "one") is None


def test_preflow_package_and_sandbox_use_same_selected_backend(documents, sample_psop_dict):
    from orchestrate.persistence.document_models import DocumentPreflowRepository
    from orchestrate.core.model.preflow import PreFlow
    from orchestrate.sandbox.store import SandboxStore
    from orchestrate.sandbox.models import StubTemplate
    from orchestrate.solution_package.manager import SolutionPackageManager

    packages = SolutionPackageManager(storage_dir="unused", documents=documents)
    packages.store_solution_package("example.pdf", {"chapter": "content"})
    packages.link_workflow("example.pdf", "wf")
    other = SolutionPackageManager(storage_dir="unused", documents=documents)
    assert other.retrieve_by_filename("example.pdf")["workflow_id"] == "wf"
    sandbox = SandboxStore(documents=documents)
    sandbox.save_templates("wf", [StubTemplate(response_text="example")])
    assert SandboxStore(documents=documents).load_templates("wf")[0].response_text == "example"


def test_job_leases_cancel_and_replay_are_visible_on_second_instance(documents):
    from orchestrate.runtime.durable_runs import JobRepository, LeaseLost

    a, b = JobRepository(documents), JobRepository(documents)
    job = a.submit("execution", {"intent": "test"}, "alice", idempotency_key="retry")
    assert b.submit("execution", {"intent": "test"}, "alice", idempotency_key="retry")["job_id"] == job["job_id"]
    claimed = a.claim(job["job_id"], "instance-A")
    assert b.claim(job["job_id"], "instance-B") is None
    a.append(job["job_id"], "instance-A", claimed["fence"], {"type": "start"})
    snapshot, rows = b.read_events(job["job_id"], "alice")
    assert snapshot["last_seq"] == rows[-1]["seq"] == 1
    assert b.get(job["job_id"], "bob") is None
    b.cancel(job["job_id"], "alice")
    with pytest.raises(LeaseLost):
        a.mark_dispatch(job["job_id"], "instance-A", claimed["fence"])


def test_dispatch_unknown_cannot_be_automatically_reclaimed(documents):
    from orchestrate.runtime.durable_runs import JobRepository, LeaseLost

    a, b = JobRepository(documents), JobRepository(documents)
    job = a.submit("execution", {"intent": "test"}, "alice")
    claimed = a.claim(job["job_id"], "instance-A")
    a.mark_dispatch(job["job_id"], "instance-A", claimed["fence"])
    with documents.transaction():
        current = documents.get("run_jobs", job["job_id"])
        current["lease_until"] = documents.now() - 1
        documents.save("run_jobs", job["job_id"], current)
    assert b.observe_stale(job["job_id"])["status"] == "reconciliation_required"
    assert b.claim(job["job_id"], "instance-B") is None
    with pytest.raises(LeaseLost):
        a.finish(job["job_id"], "instance-A", claimed["fence"], "succeeded")


def test_terminal_state_and_last_event_are_one_snapshot(documents):
    from orchestrate.runtime.durable_runs import JobRepository

    repo = JobRepository(documents)
    job = repo.submit("execution", {}, "alice")
    claimed = repo.claim(job["job_id"], "A")
    repo.finish(job["job_id"], "A", claimed["fence"], "succeeded", {"value": 1})
    snapshot, rows = repo.read_events(job["job_id"], "alice")
    assert snapshot["status"] == "succeeded"
    assert rows[-1]["seq"] == snapshot["last_seq"]
    assert rows[-1]["event"]["data"]["status"] == "succeeded"


def test_real_shared_session_revocation_and_login_race(documents):
    if isinstance(documents, FileDocuments):
        pytest.skip("Real SQL identity contract")
    from database.utils.connection_provider import SqlConnectionProvider
    from database.utils.user_store import _hash_password_bcrypt, _CURRENT_PASSWORD_SCHEME
    from orchestrate.server.sql_sessions import shared_store
    from fastapi import HTTPException

    provider = documents.provider
    conn = provider.connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users (username VARCHAR(64) PRIMARY KEY,password_hash VARCHAR(128),"
                "salt VARCHAR(64),role VARCHAR(16),must_change_password BOOLEAN,password_scheme VARCHAR(16))"
            )
            cur.execute(
                "INSERT INTO users VALUES(%s,%s,%s,%s,%s,%s)",
                ("alice", _hash_password_bcrypt("FirstPassword9!"), "", "user", False, _CURRENT_PASSWORD_SCHEME),
            )
        conn.commit()
    finally:
        conn.close()
    second = SqlConnectionProvider(provider.mode, provider.config)
    try:
        a, b = shared_store(provider), shared_store(second)
        account = a.authenticate("alice", "FirstPassword9!")
        token, _ = a.create("alice", "user", credential_snapshot=account["_auth_snapshot"])
        assert b.identity(token).username == "alice"
        old = a.authenticate("alice", "FirstPassword9!")
        b.update_password("alice", "SecondPassword9!")
        assert a.identity(token) is None
        with pytest.raises(HTTPException):
            a.create("alice", "user", credential_snapshot=old["_auth_snapshot"])
        assert b.authenticate("alice", "SecondPassword9!")
    finally:
        second.close()


def test_real_sql_job_is_observable_and_cancellable_from_fresh_process(documents):
    if isinstance(documents, FileDocuments):
        pytest.skip("File mode intentionally allows only one process")
    import subprocess
    import sys
    from orchestrate.runtime.durable_runs import JobRepository, LeaseLost

    repo = JobRepository(documents)
    job = repo.submit("sandbox", {}, "alice")
    claimed = repo.claim(job["job_id"], "first-process")
    source = """import json,sys
from database.utils.connection_provider import SqlConnectionProvider
from orchestrate.persistence.documents import SqlDocuments
from orchestrate.runtime.durable_runs import JobRepository
v=json.load(sys.stdin)
p=SqlConnectionProvider(v['mode'],v['config'])
r=JobRepository(SqlDocuments(p))
assert r.get(v['id'],'alice')['status']=='preparing'
assert r.get(v['id'],'bob') is None
assert r.cancel(v['id'],'alice')['status']=='cancelled'
p.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        input=json.dumps({"mode": documents.provider.mode, "config": documents.provider.config, "id": job["job_id"]}),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert repo.get(job["job_id"], "alice")["status"] == "cancelled"
    with pytest.raises(LeaseLost):
        repo.append(job["job_id"], "first-process", claimed["fence"], {"type": "complete"})


def test_reimport_during_generation_cannot_attach_old_workflow(documents):
    from orchestrate.solution_package.manager import SolutionPackageManager

    manager = SolutionPackageManager(storage_dir="unused", documents=documents)
    manager.store_solution_package("sample.pdf", {"flow": "old"})
    revision = manager.source_revision("sample.pdf")
    manager.store_solution_package("sample.pdf", {"flow": "new"})
    with pytest.raises(StorageConflictError):
        with documents.transaction():
            documents.save("counter", "generated", {"workflow": "old-generation"})
            manager.link_workflow("sample.pdf", "old-generation", expected_revision=revision)
    assert documents.get("counter", "generated") is None
    assert "workflow_id" not in manager.retrieve_by_filename("sample.pdf")
