# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from orchestrate.core.model.psop import PSOP
from orchestrate.persistence.execution_observation import ExecutionObservationStore
from orchestrate.server import execution_observation_api
from orchestrate.server.frontend_support_server import app
from orchestrate.server.external_auth import MachineIdentity


SOURCE = "urn:openan:host:test"
TOKEN = "test-" * 10
BATCH = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/cloudevents-batch+json"}


def event(run, seq, kind, data, source=SOURCE):
    return {"specversion": "1.0", "id": str(uuid4()), "source": source,
            "subject": run, "time": datetime.now(timezone.utc).isoformat(),
            "type": f"dev.openan.workflow.{kind}.v1", "seq": str(seq), "data": data}


@pytest.fixture
def observation(tmp_path, monkeypatch):
    from orchestrate.server import external_api, external_auth

    store = ExecutionObservationStore("file", tmp_path / "observation.sqlite3")
    store.initialize()
    monkeypatch.setenv("OPENAN_EXECUTION_HOSTS", '{"urn:openan:host:test":'
                       '{"token_env":"TEST_REPORTER_KEY","psop_ids":["psop-a"]},'
                       '"urn:openan:host:other":{"token_env":"TEST_OTHER_REPORTER_KEY","psop_ids":["*"]}}')
    monkeypatch.setenv("OPENAN_EXECUTION_BATCHES_PER_SECOND", "1000")
    monkeypatch.setenv("TEST_REPORTER_KEY", TOKEN)
    monkeypatch.setenv("TEST_OTHER_REPORTER_KEY", "other-" * 10)
    monkeypatch.setattr(execution_observation_api, "observation_store", lambda: store)
    monkeypatch.setattr(external_api, "observation_store_for_read", lambda: store)

    async def machine_identity(request, _):
        if request.url.path == "/api/v1/execution-events":
            raise HTTPException(401, "Valid center credential required")
        return MachineIdentity("query-test")

    monkeypatch.setattr(external_auth, "authenticate_external", machine_identity)
    original = PSOP.model_validate({"id": "psop-a", "name": "Original", "steps": [{
        "name": "diagnosis", "subtasks": [
            {"description": "a", "agent": "worker", "skill": "diagnose"},
            {"description": "b", "agent": "worker", "skill": "diagnose"},
        ],
    }]})
    version = store.publish(original)
    return TestClient(app, base_url="https://testserver"), store, version, original


def post(client, *events, headers=BATCH):
    return client.post("/api/v1/execution-events", json=events, headers=headers)


def start(run, version, source=SOURCE):
    return event(run, 1, "execution.started",
                 {"psop_id": version["id"], "psop_revision": version["revision"]}, source)


def task(ref=0, attempt=1, task_id=None):
    return {"step_ref": "s0", "task_ref": f"s0/t{ref}",
            "task_id": task_id or str(uuid4()), "attempt": attempt}


def test_only_admin_can_delete_auto_reported_record(observation, account_session, monkeypatch):
    from orchestrate.server import auth, frontend_support_server

    client, store, version, _ = observation
    monkeypatch.setattr(frontend_support_server, "observation_store", lambda: store)
    run = str(uuid4())
    assert post(client, start(run, version)).status_code == 200
    ordinary_token, _ = auth.get_session_store().create("ordinary-user", "user")
    path = f"/rest/v1/orchestrate/execution-records/{run}"
    refused = client.delete(path, headers={"Authorization": f"Bearer {ordinary_token}"})
    assert refused.status_code == 403, refused.text
    assert store.detail(run) is not None
    deleted = client.delete(path, headers=account_session)
    assert deleted.status_code == 200, deleted.text
    assert store.detail(run) is None


def test_timeline_pages_replay_early_progress_before_the_frozen_cursor(observation, account_session):
    client, store, version, _ = observation
    run = str(uuid4())
    node = task()
    entries = [start(run, version), event(run, 2, "task.started", node),
               event(run, 3, "task.progressed", node | {"summary": "early reply"})]
    entries.extend(event(run, seq, "task.progressed", node | {"summary": "later"})
                   for seq in range(4, 1006))
    for offset in range(0, len(entries), 50):
        store.ingest(entries[offset:offset + 50], {"*"})
    record = store.detail(run)
    assert record["events_truncated"]
    assert not any(item["data"].get("summary") == "early reply" for item in record["events"])
    store.ingest([event(run, 1006, "execution.finished", {"outcome": "succeeded"})], {"*"})

    path = f"/rest/v1/orchestrate/executions/{run}/events"
    options = {"view": "timeline", "through_cursor": record["last_cursor"]}
    first = client.get(path, params=options | {"limit": 1}, headers=account_session)
    assert first.status_code == 200, first.text
    assert first.json() == {"events": [], "next_cursor": "1"}

    cursor, events = first.json()["next_cursor"], []
    while cursor != record["last_cursor"]:
        response = client.get(path, params=options | {"after_cursor": cursor, "limit": 500},
                              headers=account_session)
        assert response.status_code == 200, response.text
        page = response.json()
        assert int(cursor) < int(page["next_cursor"]) <= int(record["last_cursor"])
        events.extend(row["event"] for row in page["events"])
        cursor = page["next_cursor"]

    assert events[1]["type"] == "task_status_changed"
    assert events[1]["data"]["summary"] == "early reply"
    assert events[-1]["seq"] == record["last_cursor"]
    raw = client.get(path, params={"limit": 1}, headers=account_session).json()
    assert raw["events"][0]["event"]["type"] == start(run, version)["type"]


def test_exact_current_revision_requires_no_archive(observation, monkeypatch):
    from orchestrate.server import external_api

    client, _, version, current = observation
    monkeypatch.setattr(external_api, "observation_enabled", lambda: False)
    monkeypatch.setattr(external_api.SharedHandlers, "retrieval",
                        lambda: SimpleNamespace(get_psop_by_id=lambda _: current))
    path = f"/api/v1/orchestrate/psop/{current.id}"
    original = client.get(path, params={"revision": version["revision"]})
    assert original.status_code == 200, original.text
    assert original.json()["data"]["revision"] == version["revision"]
    current.name = "Newly published version"
    assert client.get(path, params={"revision": version["revision"]}).status_code == 404


def test_parallel_runs_out_of_order_terminal_cursor_and_revision(observation, monkeypatch):
    client, store, version, original = observation
    a, b = str(uuid4()), str(uuid4())
    first, second = task(), task(1)
    other_first, other_second = task(), task(1)
    messages = [
        (start(a, version), event(a, 2, "task.started", first), event(a, 3, "task.started", second)),
        (start(b, version), event(b, 2, "task.started", other_first), event(b, 3, "task.started", other_second)),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda batch: post(client, *batch).status_code, messages)) == [200, 200]
    final_a = event(a, 6, "execution.finished", {"outcome": "succeeded"})
    assert post(client, final_a).json()["missing_ranges"] == [["4", "5"]]
    partial = store.detail(a)
    assert partial["reported_outcome"] == "succeeded"
    assert partial["event_coverage"] == "gapped"
    assert partial["projected_through"] == "3"

    second_result = event(a, 5, "task.finished", second | {"outcome": "succeeded"})
    interaction = event(a, 4, "task.progressed", first | {
        "interaction": {"kind": "negotiation", "phase": "resolved"},
    })
    assert post(client, interaction, second_result).json()["contiguous_through"] == "6"
    assert post(client, interaction, second_result).json()["duplicates"] == 2
    assert post(client, event(a, 7, "task.started", first)).status_code == 409
    replay = client.get(f"/api/v1/executions/{a}/events?after_cursor={partial['last_cursor']}").json()
    assert [row["event"]["seq"] for row in replay["events"]] == ["4", "5"]
    reading = FastAPI()
    reading.include_router(execution_observation_api.router)
    from orchestrate.server import auth
    monkeypatch.setattr(auth, "require_session_identity", lambda request: None)
    with TestClient(reading) as stream_reader:
        path = f"/rest/v1/orchestrate/executions/{a}/stream"
        replay_stream = stream_reader.get(path, headers={"Last-Event-ID": partial["last_cursor"]})
        assert 'id: 5' in replay_stream.text and 'id: 6' in replay_stream.text
        assert 'id: 4' not in replay_stream.text
        response = stream_reader.get(path, headers={"Last-Event-ID": "6"})
        assert response.status_code == 204
    assert store.detail(a)["event_coverage"] == "complete"
    assert any(row["type"] == "negotiation_resolved" for row in store.detail(a)["events"])
    assert store.detail(b)["reported_outcome"] is None
    assert store.detail(b)["execution_history"][0]["task_id"] == other_first["task_id"]
    assert {row["execution_id"] for row in store.list_runs()} == {a, b}
    newer = store.publish(original.model_copy(update={"name": "Updated"}))
    assert newer["revision"] != version["revision"]
    assert store.detail(a)["final_psop"]["name"] == "Original"


def test_loaded_psop_can_report_using_its_existing_center_identity(observation, monkeypatch):
    from orchestrate.server import external_api, external_auth

    client, store, version, psop = observation
    monkeypatch.delenv("OPENAN_EXECUTION_HOSTS")
    monkeypatch.setattr(external_api.SharedHandlers, "retrieval",
                        lambda: SimpleNamespace(get_psop_by_id=lambda _: psop))

    async def authenticate(request, _):
        identities = {
            "Bearer first-session": MachineIdentity("owner"),
            "Bearer renewed-session": MachineIdentity("owner"),
            "Bearer second-session": MachineIdentity("other"),
        }
        identity = identities.get(request.headers.get("authorization"))
        if identity is None:
            raise HTTPException(401, "Valid center credential required")
        return identity

    monkeypatch.setattr(external_auth, "authenticate_external", authenticate)
    original_headers = BATCH | {"Authorization": "Bearer first-session"}
    renewed_headers = BATCH | {"Authorization": "Bearer renewed-session"}
    other_headers = BATCH | {"Authorization": "Bearer second-session"}
    path = "/api/v1/orchestrate/psop/psop-a"
    loaded = client.get(path, headers=original_headers).json()["data"]
    other = client.get(path, headers=other_headers).json()["data"]
    assert loaded["revision"] == version["revision"]
    source = loaded["execution_reporting_source"]
    assert source != other["execution_reporting_source"]
    assert client.get(path, headers=renewed_headers).json()["data"]["execution_reporting_source"] == source

    run = str(uuid4())
    opening = start(run, version, source)
    assert post(client, opening, headers=BATCH).status_code == 401
    assert post(client, opening, headers=other_headers).json()["code"] == "SOURCE_MISMATCH"
    assert post(client, opening, headers=original_headers).status_code == 200
    closing_data = {"outcome": "succeeded"}
    forged = event(run, 2, "execution.finished", closing_data, other["execution_reporting_source"])
    assert post(client, forged, headers=other_headers).json()["code"] == "OWNER_MISMATCH"
    assert post(client, event(run, 2, "execution.finished", closing_data, source),
                headers=renewed_headers).status_code == 200
    assert store.detail(run)["reported_outcome"] == "succeeded"


def test_https_requirement_accepts_a_trusted_reverse_proxy(monkeypatch):
    import common.util.config_util as config_util

    def request(client_host):
        return SimpleNamespace(
            url=SimpleNamespace(scheme="http"),
            client=SimpleNamespace(host=client_host),
            headers={"x-forwarded-proto": "https"},
        )

    monkeypatch.setattr(config_util, "get_conf", lambda: {"forwarded_allow_ips": "10.0.0.5"})
    assert execution_observation_api._secure_transport(request("10.0.0.5")) is True
    assert execution_observation_api._secure_transport(request("10.0.0.6")) is False


def test_projects_business_input_and_result_for_each_task(observation):
    client, store, version, _ = observation
    run = str(uuid4())
    first, second = task(), task(1)
    assert post(client, start(run, version),
                event(run, 2, "task.started", first),
                event(run, 3, "task.started", second)).status_code == 200

    too_long = event(run, 4, "task.progressed", first | {"input_summary": "x" * 2049})
    assert post(client, too_long).status_code == 422
    assert post(client,
                event(run, 4, "task.progressed", first | {"input_summary": "Inspect City1 line"}),
                event(run, 5, "task.progressed", second | {"input_summary": "Inspect City2 line"}),
                event(run, 6, "task.finished", second | {"outcome": "succeeded",
                      "result": {"summary": "City2 healthy"}}),
                event(run, 7, "task.finished", first | {"outcome": "succeeded",
                      "result": {"summary": "City1 optical fault"}}),
                event(run, 8, "execution.finished", {"outcome": "succeeded"})).status_code == 200
    rows = {row["task_ref"]: row for row in store.detail(run)["execution_history"]}
    assert rows["s0/t0"]["input_summary"] == "Inspect City1 line"
    assert rows["s0/t0"]["result"]["summary"] == "City1 optical fault"
    assert rows["s0/t1"]["input_summary"] == "Inspect City2 line"
    assert rows["s0/t1"]["result"]["summary"] == "City2 healthy"


def test_revision_preserves_authored_ids_and_legacy_ids_are_stable(observation):
    _, store, _, _ = observation
    raw = {"id": "legacy-psop", "name": "Legacy", "steps": [
        {"name": "step", "subtasks": [
            {"description": "existing", "agent": "host", "skill": "one", "task_id": "authored-id"},
            {"description": "legacy", "agent": "host", "skill": "two"},
        ]},
    ]}
    published = store.publish(PSOP.model_validate(raw))
    raw["steps"][0]["subtasks"][1]["status"] = "failed"
    assert store.publish(PSOP.model_validate(raw))["revision"] == published["revision"]
    original_tasks = published["steps"][0]["subtasks"]
    assert original_tasks[0]["task_id"] == "authored-id"
    assert original_tasks[1]["task_id"] == PSOP.model_validate(raw).steps[0].subtasks[1].task_id
    assert "status" not in original_tasks[1]
    raw["steps"][0]["subtasks"][0]["task_id"] = "different-authored-id"
    changed = store.publish(PSOP.model_validate(raw))
    assert changed["revision"] != published["revision"]
    assert store.version(raw["id"], published["revision"]) == published


def test_save_publishes_even_when_the_handler_returns_nothing(observation, monkeypatch):
    from common.custom import HandlerRegistry, InterfaceType
    from orchestrate.handlers.dispatch import get_storage_handler
    from orchestrate.persistence import execution_observation

    _, store, _, original = observation
    psop = original.model_copy(update={"name": "Silent handler"})
    monkeypatch.setattr(execution_observation, "observation_store", lambda: store)
    monkeypatch.setattr(HandlerRegistry, "get_handler",
                        lambda *args, **kwargs: SimpleNamespace(handle=lambda value: None))

    assert get_storage_handler(InterfaceType.SAVE_PSOP).handle(psop) is None
    assert store.published_revision(psop)


def test_save_publishes_revision_and_get_survives_observation_failure(observation, monkeypatch):
    from common.custom import HandlerRegistry, InterfaceType
    from orchestrate.handlers.dispatch import get_storage_handler
    from orchestrate.persistence import execution_observation
    from orchestrate.server import external_api

    client, store, _, original = observation
    psop = original.model_copy(update={"name": "Published update"})
    monkeypatch.setattr(execution_observation, "observation_store", lambda: store)
    monkeypatch.setattr(HandlerRegistry, "get_handler",
                        lambda *args, **kwargs: SimpleNamespace(handle=lambda value: value.id))
    monkeypatch.setattr(external_api.SharedHandlers, "retrieval",
                        lambda: SimpleNamespace(get_psop_by_id=lambda psop_id: psop))
    assert get_storage_handler(InterfaceType.SAVE_PSOP).handle(psop) == psop.id
    path = f"/api/v1/orchestrate/psop/{psop.id}"
    current = client.get(path).json()["data"]
    revision = current["revision"]
    assert revision == store.published_revision(psop) and revision
    historical = client.get(path, params={"revision": revision}).json()["data"]
    assert historical["name"] == psop.name
    # The fixture definition omitted task IDs. Normal and revisioned reads
    # must nevertheless return the same stable identities.
    assert [task["task_id"] for task in current["steps"][0]["subtasks"]] == [
        task["task_id"] for task in historical["steps"][0]["subtasks"]
    ]

    def unavailable():
        raise OSError("Observation unavailable")

    monkeypatch.setattr(external_api, "observation_store_for_read", unavailable)
    response = client.get(path)
    assert response.status_code == 200 and response.json()["data"]["revision"] is None
    assert response.json()["data"]["name"] == psop.name


def test_uninitialized_observation_read_does_not_create_sqlite_file(observation, tmp_path):
    _, _, _, psop = observation
    path = tmp_path / "observer-not-initialized.sqlite3"
    reader = ExecutionObservationStore("file", path)
    with pytest.raises(sqlite3.OperationalError):
        reader.published_revision(psop)
    assert not path.exists()


def test_sequence_window_recovers_only_durably_absent_ordinals(observation):
    client, store, version, _ = observation
    run, binding = str(uuid4()), task()
    assert post(client, start(run, version), event(run, 4, "task.started", binding),
                event(run, 6, "task.progressed", binding)).status_code == 200
    rejected = post(client, event(run, 2, "task.started", binding),
                    event(run, 1027, "task.progressed", binding))
    assert rejected.status_code == 409
    problem = rejected.json()
    assert problem["code"] == "SEQUENCE_WINDOW" and problem["event_index"] == 1
    assert problem["contiguous_through"] == "1"
    assert problem["missing_ranges"] == [["2", "3"], ["5", "5"], ["7", "1025"]]
    assert [row["event"]["seq"] for row in store.events(run, 0, 100)] == ["1", "4", "6"]


def test_stream_closes_on_session_revocation_and_expiry(observation, monkeypatch):
    from orchestrate.server import auth

    client, store, version, _ = observation
    run = str(uuid4())
    assert post(client, start(run, version)).status_code == 200
    app = FastAPI()
    app.include_router(execution_observation_api.router)
    path = f"/rest/v1/orchestrate/executions/{run}/stream"
    checks = 0

    def validate_session(request):
        nonlocal checks
        checks += 1
        if checks > 1:
            raise HTTPException(401, "Expired")

    monkeypatch.setattr(auth, "require_session_identity", validate_session)
    with TestClient(app) as reader:
        replay = reader.get(path)
        assert "id: 1" in replay.text and "event: stream_error" in replay.text
        assert checks == 2

        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        with store.transaction(write=True) as query:
            query("UPDATE observation_runs SET last_received_at=? WHERE id=?", (stale, run))
        monkeypatch.setattr(auth, "require_session_identity", lambda request: None)
        replay = reader.get(path)
        assert "id: 1" in replay.text and "event: stream_end" in replay.text
        assert '"state":"expired"' in replay.text
        tail = reader.get(path, headers={"Last-Event-ID": "1"})
        assert tail.status_code == 204
        assert tail.headers["X-Execution-Stream-State"] == "expired"
        assert tail.headers["X-Execution-Cursor"] == "1"


def test_permanent_gap_and_late_old_task_attempt(observation):
    client, store, version, _ = observation
    run = str(uuid4())
    identity = task()
    retry = identity | {"attempt": 2}
    assert post(client, start(run, version), event(run, 2, "step.started", {"step_ref": "s0"})).status_code == 200
    assert post(client, event(run, 4, "task.started", retry)).status_code == 200
    assert store.detail(run)["projected_through"] == "2"
    assert post(client, event(run, 3, "execution.gap.declared", {"reason_code": "spool_loss"})).status_code == 200
    assert post(client, event(run, 5, "task.finished", identity | {"outcome": "failed"})).status_code == 200
    assert store.detail(run)["execution_history"][0].get("outcome") is None
    # More than one receiving window can still be ingested after a declared loss.
    for begin in range(6, 1040, 100):
        batch = [event(run, seq, "task.progressed", retry) for seq in range(begin, min(begin + 100, 1040))]
        assert post(client, *batch).status_code == 200
    assert post(client, event(run, 1040, "task.finished", retry | {"outcome": "succeeded"}),
                event(run, 1041, "step.finished", {"step_ref": "s0", "outcome": "failed"}),
                event(run, 1042, "execution.finished", {"outcome": "failed"})).status_code == 200
    record = store.detail(run)
    assert record["event_coverage"] == "gapped"
    assert record["declared_gaps"] == 1
    assert record["projected_through"] == "1042"
    assert record["execution_history"][0]["outcome"] == "succeeded"
    assert record["step_history"][0]["outcome"] == "failed"
    assert "started_at" in record["step_history"][0]
    assert not any(entry["type"] == "step_start" for entry in record["events"])


def test_reject_wrong_host_and_rollback_conflicting_batch(observation):
    client, store, version, _ = observation
    run = str(uuid4())
    beginning = start(run, version)
    assert post(client, beginning, headers=BATCH | {"Authorization": "Bearer invalid"}).status_code == 401
    assert post(client, start(str(uuid4()), version | {"id": "another-flow"})).json()["code"] == "PSOP_FORBIDDEN"
    assert post(client, beginning).status_code == 200
    other = "urn:openan:host:other"
    headers = BATCH | {"Authorization": "Bearer " + "other-" * 10}
    assert post(client, event(run, 2, "task.started", task(), other), headers=headers).status_code == 403
    assert post(client, event(run, 2, "task.started", task()), beginning | {
        "time": datetime.now(timezone.utc).isoformat(),
    }).json()["code"] == "EVENT_ID_CONFLICT"
    assert len(store.events(run, 0, 25)) == 1
    assert store.hide(run)
    assert post(client, beginning).json()["duplicates"] == 1
    assert post(client, event(run, 2, "task.started", task())).status_code == 410


def test_single_event_preserves_valid_trace_context(observation):
    client, store, version, _ = observation
    run = str(uuid4())
    trace = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    entry = start(run, version) | {"traceparent": trace, "tracestate": "vendor=sample"}
    headers = BATCH | {"Content-Type": "application/cloudevents+json", "traceparent": trace}
    response = client.post("/api/v1/execution-events", json=entry, headers=headers)
    assert response.json()["code"] == "TRACE_CONTEXT_MISMATCH"
    headers["tracestate"] = "vendor=sample"
    assert client.post("/api/v1/execution-events", json=entry, headers=headers).status_code == 200
    assert store.events(run, 0, 1)[0]["event"]["traceparent"] == trace


def test_conflicting_attempt_outcomes_do_not_rewrite_projected_result(observation):
    client, store, version, _ = observation
    run = str(uuid4())
    binding = task()
    assert post(client, start(run, version), event(run, 2, "task.started", binding),
                event(run, 3, "task.finished", binding | {"outcome": "succeeded"}),
                event(run, 4, "task.finished", binding | {"outcome": "failed"})).status_code == 200
    record = store.detail(run)
    assert record["execution_history"][0]["outcome"] == "succeeded"
    assert record["projection_anomaly"] is True


@pytest.mark.parametrize("mode", ["postgresql", "mysql"])
def test_observation_transaction_on_real_sql_backend(mode, monkeypatch):
    raw_config = os.environ.get(f"ORCH_{mode.upper()}_OBSERVATION_TEST_CONFIG")
    if not raw_config:
        pytest.skip(f"Set an isolated {mode} observation test database")
    from types import SimpleNamespace

    from orchestrate.persistence import execution_observation
    from orchestrate.persistence.sql_backend import SqlPersistenceBackend

    backend = SqlPersistenceBackend(mode, {"connection_config": json.loads(raw_config)})
    monkeypatch.setattr(execution_observation, "current_context", lambda: SimpleNamespace(backend=backend))
    try:
        store = ExecutionObservationStore(mode)
        store.initialize()
        graph = store.publish(PSOP.model_validate({
            "id": str(uuid4()), "name": "SQL observation smoke",
            "steps": [{"name": "test", "subtasks": [{"description": "observe", "agent": "x", "skill": "x"}]}],
        }))
        run = str(uuid4())
        beginning = start(run, graph)
        binding = task()
        assert store.ingest([beginning], {"*"})["accepted"] == 1
        end = event(run, 4, "execution.finished", {"outcome": "succeeded"})
        assert store.ingest([end], {"*"})["missing_ranges"] == [["2", "3"]]
        middle = event(run, 2, "task.started", binding)
        late = event(run, 3, "task.finished", binding | {"outcome": "succeeded"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda batch: store.ingest(batch, {"*"}), [[middle, late], [middle, late]]))
        assert sorted(response["accepted"] for response in responses) == [0, 2]
        assert sorted(response["duplicates"] for response in responses) == [0, 2]
        reopened = ExecutionObservationStore(mode)
        assert reopened.detail(run)["event_coverage"] == "complete"
        assert [row["event"]["seq"] for row in reopened.events(run, 2, 10)] == ["2", "3"]
    finally:
        backend.close()


@pytest.mark.asyncio
async def test_real_python_runner_posts_parallel_runs(observation, tmp_path):
    import asyncio
    from contextlib import closing
    import socket
    from threading import Thread

    import uvicorn

    pytest.importorskip("workflow_engine.observation")
    from workflow_engine import ControlPoint, ExecutionReporter, execute_psop
    from workflow_engine.core.models import TaskResult

    _, store, _, original = observation
    workflow = original.model_dump(mode="json")
    workflow["steps"][0]["type"] = "SelfLoop"
    version = store.publish(PSOP.model_validate(workflow))

    class LocalTasks(ControlPoint):
        async def on_self_task(self, request):
            await asyncio.sleep(.03)
            return TaskResult(success=True, outputs=({"score": 7, "secret": "never send"},))

    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        thread = Thread(target=server.run, kwargs={"sockets": [server_socket]}, daemon=True)
        thread.start()
        port = server_socket.getsockname()[1]
        reporter = ExecutionReporter(
            f"http://127.0.0.1:{port}/api/v1/execution-events", TOKEN, SOURCE,
            tmp_path / "spool", output_keys=["score"],
        )

        async def run():
            return [entry async for entry in execute_psop(version, [], LocalTasks(), reporter=reporter)]

        try:
            results = await asyncio.gather(run(), run())
            assert all(any(entry["type"] == "complete" for entry in result) for result in results)
            for _ in range(100):
                records = store.list_runs()
                if len(records) == 2 and all(record["event_coverage"] == "complete" for record in records):
                    break
                await asyncio.sleep(.05)
            assert len(records) == 2
            all_ids = set()
            for record in records:
                detail = store.detail(record["execution_id"])
                assert record["event_coverage"] == "complete"
                assert len(detail["execution_history"]) == 2
                for task_result in detail["execution_history"]:
                    assert task_result["task_id"] not in all_ids
                    all_ids.add(task_result["task_id"])
                    assert task_result["result"]["outputs"] == {"score": 7}
                assert "never send" not in str(detail)
        finally:
            await asyncio.to_thread(reporter.close)
            server.should_exit = True
            await asyncio.to_thread(thread.join, 5)
