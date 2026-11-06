# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Dispatch ambiguity, snapshot/replay, cancellation and migration regression tests."""

import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from orchestrate.persistence.documents import FileDocuments
from orchestrate.persistence.errors import StorageConflictError
from orchestrate.server import durable_api
from orchestrate.server.durable_api import RunCoordinator
from orchestrate.runtime.durable_runs import JobRepository


def request_spec():
    return dict(
        intent="test",
        target_agent="Host",
        lang="zh",
        select_template=True,
        psop=None,
        resolution_request={},
        verified_caller_id="alice",
        agent_cards=[{"name": "Host"}],
        identity={"credential_revision": hashlib.sha256(b"configured-hash").hexdigest()},
    )


class ObservedEngine:
    release = None
    sent = 0

    def __init__(self, *args, **kwargs):
        pass

    async def events(self, intent, *, dispatch_guard, execution_id, **kwargs):
        yield {"type": "psop_update", "data": {"psop": {"id": "selected", "name": "Selected"}}}
        await dispatch_guard({"psop": {"id": "selected"}, "metadata": {"frozen": True}})
        type(self).sent += 1
        yield {"type": "start", "data": {"phase": "dispatching"}}
        await type(self).release.wait()
        yield {"type": "complete", "data": {}}


@pytest.mark.asyncio
async def test_observing_from_another_instance_does_not_create_or_cancel_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_api, "get_conf", lambda: {"access_password": "configured-hash"})
    ObservedEngine.release = asyncio.Event()
    ObservedEngine.sent = 0
    docs = FileDocuments(tmp_path)
    a = RunCoordinator(docs, engine_factory=ObservedEngine)
    b = RunCoordinator(FileDocuments(tmp_path), engine_factory=ObservedEngine)
    job = a.repo.submit("execution", request_spec(), "alice")
    claimed = a.repo.claim(job["job_id"], a.owner)
    task = asyncio.create_task(a._execute(claimed))
    try:
        for _ in range(100):
            if ObservedEngine.sent:
                break
            await asyncio.sleep(0.01)
        assert ObservedEngine.sent == 1
        assert b.repo.get(job["job_id"], "bob") is None
        state, rows = b.repo.read_events(job["job_id"], "alice")
        assert state["dispatch_envelope"]["metadata"]["frozen"]
        assert state["current_psop"]["id"] == "selected"
        assert rows[-1]["seq"] == state["last_seq"]
        assert not task.done()
        assert b.repo.claim(job["job_id"], b.owner) is None
        ObservedEngine.release.set()
        await task
        state, rows = b.repo.read_events(job["job_id"], "alice")
        assert state["status"] == "succeeded"
        assert rows[-2]["event"]["type"] == "complete"
        assert rows[-1]["event"]["data"]["status"] == "succeeded"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_on_other_instance_retains_unknown_remote_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_api, "get_conf", lambda: {"access_password": "configured-hash"})
    ObservedEngine.release = asyncio.Event()
    ObservedEngine.sent = 0
    docs = FileDocuments(tmp_path)
    a = RunCoordinator(docs, engine_factory=ObservedEngine, lease_seconds=1)
    b = JobRepository(FileDocuments(tmp_path))
    job = b.submit("execution", request_spec(), "alice")
    task = asyncio.create_task(a._execute(b.claim(job["job_id"], a.owner)))
    for _ in range(100):
        if ObservedEngine.sent:
            break
        await asyncio.sleep(0.01)
    assert ObservedEngine.sent == 1
    b.cancel(job["job_id"], "alice")
    await asyncio.wait_for(task, 5)
    state = b.get(job["job_id"], "alice")
    assert state["status"] == "reconciliation_required"
    assert b.claim(job["job_id"], "new-owner") is None
    assert ObservedEngine.sent == 1


def test_migration_dry_run_and_missing_checkpoint_verify_actual_output(tmp_path):
    from scripts.migrate_operational_storage import migrate

    source, target = tmp_path / "source", FileDocuments(tmp_path / "target")
    inputs = FileDocuments(source)
    inputs.save("solution_packages", "example", {"pdf_filename": "example.pdf", "chapters": {}})
    assert migrate(source, None, target_identity="not-used", dry_run=True)["planned"] == 1
    assert target.list("storage_migrations") == []
    assert migrate(source, target, target_identity="db-one")["imported"] == 1
    assert migrate(source, target, target_identity="db-one")["verified"] == 1
    # A different target must be populated, regardless of previous successes.
    other = FileDocuments(tmp_path / "other")
    assert migrate(source, other, target_identity="db-two")["imported"] == 1
    inputs.save("solution_packages", "example", {"pdf_filename": "changed.pdf"})
    with pytest.raises(StorageConflictError):
        migrate(source, target, target_identity="db-one")


def test_cluster_rejects_file_backend_and_missing_schema_is_not_auto_created(tmp_path):
    from orchestrate.persistence.factory import create
    from orchestrate.persistence.errors import StorageConfigError

    with pytest.raises(StorageConfigError):
        create("file", {"deployment_mode": "cluster"})


def test_history_alias_cannot_bypass_run_owner_or_deletion(tmp_path, monkeypatch):
    from orchestrate.server.auth import SessionIdentity

    docs = FileDocuments(tmp_path)
    repo = JobRepository(docs)
    job = repo.submit("execution", {}, "user:alice")
    monkeypatch.setattr(durable_api, "current_context", lambda: SimpleNamespace(documents=docs))
    req = Request({"type": "http", "headers": []})
    req.state.user_identity = SessionIdentity("alice", "user")
    assert durable_api.history_visible(job["job_id"], req)
    req.state.user_identity = SessionIdentity("bob", "user")
    assert not durable_api.history_visible(job["job_id"], req)
    req.state.user_identity = SessionIdentity("alice", "user")
    repo.remove(job["job_id"], "user:alice")
    assert not durable_api.history_visible(job["job_id"], req)


@pytest.mark.asyncio
async def test_two_sandbox_instances_can_query_and_cancel_inflight_run(tmp_path, monkeypatch):
    from orchestrate.sandbox.service import SandboxService
    from orchestrate.sandbox.store import SandboxStore
    from orchestrate.core.model.psop import PSOP

    entered = asyncio.Event()

    async def blocked(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", blocked)
    a = SandboxService(lambda **kwargs: None, SandboxStore(tmp_path))
    b = SandboxService(lambda **kwargs: None, SandboxStore(tmp_path))
    job = await a.start(PSOP(id="wf", name="Wf", steps=[]), [], principal="alice")
    await entered.wait()
    assert b.status(job, "alice")["status"] == "running"
    assert b.status(job, "bob") is None
    assert await b.cancel_and_delete(job, "alice")
    await asyncio.wait_for(a.wait(job), 5)
    assert a.status(job, "alice") is None
    assert a.store.load_report(job) is None


@pytest.mark.asyncio
async def test_sandbox_queued_before_restart_is_claimed_without_new_id(tmp_path, monkeypatch):
    from orchestrate.sandbox.service import SandboxService
    from orchestrate.sandbox.store import SandboxStore
    from orchestrate.sandbox.models import SandboxRunReport, StubScenario
    from orchestrate.core.model.psop import PSOP
    from orchestrate.validation.sandbox_validator import SandboxCheckStatus

    store = SandboxStore(tmp_path)
    repo = JobRepository(store.documents)
    request = dict(
        psop=PSOP(id="wf", name="Wf", steps=[]).model_dump(mode="json"),
        agent_cards=[],
        scenario="success",
        runtime_intent="test",
        templates=[],
        lang="zh",
    )
    queued = repo.submit("sandbox", request, "alice")

    async def succeed(psop, cards, point, *, verification_id, **kwargs):
        return SandboxRunReport(
            verification_id=verification_id,
            workflow_id=psop.id,
            workflow_name=psop.name,
            scenario=StubScenario.SUCCESS,
            verdict=SandboxCheckStatus.PASS,
        )

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", succeed)
    service = SandboxService(lambda **kwargs: None, store)
    service.start_scheduler()
    try:
        for _ in range(100):
            if repo.get(queued["job_id"])["status"] == "succeeded":
                break
            await asyncio.sleep(0.02)
        assert repo.get(queued["job_id"])["status"] == "succeeded"
        assert service.report(queued["job_id"], "alice")["report"]["verification_id"] == queued["job_id"]
        assert len(repo.list()) == 1
    finally:
        await service.aclose()


def test_history_failure_rolls_back_final_state_and_terminal_event(tmp_path):
    from unittest.mock import Mock

    documents = FileDocuments(tmp_path)
    history = Mock()
    history.save.side_effect = ValueError("history persistence failed")
    coordinator = RunCoordinator(documents, history_repository=history)
    job = coordinator.repo.submit("execution", request_spec(), "alice")
    claimed = coordinator.repo.claim(job["job_id"], coordinator.owner)
    with pytest.raises(ValueError):
        coordinator._finish(job["job_id"], claimed["fence"], "succeeded", {}, None, {"type": "complete"})
    current, events = coordinator.repo.read_events(job["job_id"], "alice")
    assert current["status"] == "preparing"
    assert events == []


@pytest.mark.parametrize("retained", [2000, 5])
def test_sandbox_events_include_all_pages_and_explicit_retention_marker(tmp_path, retained):
    from orchestrate.sandbox.service import SandboxService
    from orchestrate.sandbox.store import SandboxStore

    service = SandboxService(lambda **kwargs: None, SandboxStore(tmp_path))
    repo = JobRepository(service.store.documents, event_limit=retained)
    job = repo.submit("sandbox", {}, "alice")
    claimed = repo.claim(job["job_id"], "worker")
    for index in range(205):
        repo.append(job["job_id"], "worker", claimed["fence"], {"type": "progress", "data": {"index": index}})
    events = service.events(job["job_id"], "alice")
    if retained == 5:
        assert events[0] == {"type": "events_truncated", "data": {"through_seq": 200}}
        events = events[1:]
    assert [event["data"]["index"] for event in events] == list(range(max(0, 205 - retained), 205))
    assert service.events(job["job_id"], "bob") == []
