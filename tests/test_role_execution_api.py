# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""HTTP contract for POST /rest/v1/orchestrate/role-execution/preview."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.core.model.psop import PSOP
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.server.frontend_support_server import app

BASE = "/rest/v1/orchestrate"

SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
OPTIMIZER = "ran-energy-optimizer"


def _approve_all(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "review_status":
                value[key] = "approved"
            else:
                _approve_all(item)
    elif isinstance(value, list):
        for item in value:
            _approve_all(item)


def _approved_catalog_file(tmp_path):
    data = json.loads(SEED_CATALOG.read_text(encoding="utf-8"))
    _approve_all(data)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _registry_file(tmp_path):
    from orchestrate.core.model.instance_binding import (
        InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
    )

    scope = ServiceScope(tenant="t", site="city-a", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed", priority=10, scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
    ])
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    return str(path)


def _role_psop():
    return PSOP.model_validate(dict(
        id="wf-role-pilot", name="Role pilot", catalog_version="pilot-wireless-v1",
        steps=[dict(name="explore", subtasks=[dict(
            task_id="t1", description="Explore energy intent", binding="role",
            agent=OPTIMIZER, skill="explore-energy-intent", role_version="1.0.0",
        )])],
    ))


def _plain_psop():
    return PSOP.model_validate(dict(
        id="wf-plain", name="Plain",
        steps=[dict(name="work", subtasks=[dict(
            task_id="t1", description="Do work", binding="instance",
            agent="Legacy Agent", skill="Legacy Skill",
        )])],
    ))


@pytest.fixture
def resolution_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                        lambda: ["inst-a"])
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_execution_scope",
                        lambda: None)
    return SimpleNamespace(catalog_path=_approved_catalog_file(tmp_path))


@pytest.fixture
def stored_psop(monkeypatch):
    psop = _role_psop()
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        get_psop_by_id=lambda psop_id: psop if psop_id == psop.id else None))
    return psop


@pytest.fixture
def cards(monkeypatch):
    from samples.role_pilot.technical_server import pilot_card

    monkeypatch.setattr("orchestrate.server.role_execution_api.get_agent_cards",
                        lambda: _async_done([pilot_card("a", 1)]))
    # The legacy GET /execute route resolves its own imported symbol.
    monkeypatch.setattr("orchestrate.server.frontend_support_server.get_agent_cards",
                        lambda: _async_done([pilot_card("a", 1)]))
    return [pilot_card("a", 1)]


def _async_done(cards):
    async def _cards():
        return cards

    return _cards()


@pytest.fixture
def client(account_session):
    with TestClient(app, headers=account_session) as test_client:
        yield test_client


def test_preview_returns_contract_shape(client, stored_psop, cards, resolution_inputs):
    response = client.post(f"{BASE}/role-execution/preview",
                           json={"psop_id": stored_psop.id, "scope": "t/city-a/b"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["psop_id"] == stored_psop.id
    assert data["can_execute"] is True
    assert len(data["resolution_fingerprint"]) == 64
    assert "execution_id" not in data
    unit = data["units"][0]
    assert unit["unit_id"] == "task:t1"
    assert unit["current_selection"]["instance_id"] == "inst-a"
    assert unit["current_selection"]["agent_name"] == "Technical RAN A"
    assert unit["current_selection"]["priority"] == 10
    assert unit["current_selection"]["selection_reason"] == "highest_priority"
    assert "endpoint" not in unit["current_selection"]
    assert data["caller_id"] == "fixture-admin"
    assert data["execution_scope"] == "t/city-a/b"
    assert data["catalog_version"] == "pilot-wireless-v1"
    assert data["config_version"] == "cfg-v1"
    assert data["issues"] == []


def test_preview_writes_no_execution_record_and_no_dispatch(client, stored_psop, cards,
                                                            resolution_inputs):
    with patch("orchestrate.handlers.dispatch.get_storage_handler") as storage, \
            patch("orchestrate.server.sse_executor.dispatch_intent_sse") as dispatch:
        response = client.post(f"{BASE}/role-execution/preview",
                               json={"psop_id": stored_psop.id, "scope": "t/city-a/b"})

    assert response.status_code == 200
    storage.assert_not_called()
    dispatch.assert_not_called()


def test_preview_accepts_overrides_and_tie_break(client, stored_psop, cards, resolution_inputs):
    response = client.post(f"{BASE}/role-execution/preview", json={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "task_overrides": {"t1": "inst-a"}, "tie_break": "instance_id",
    })

    data = response.json()["data"]
    assert data["units"][0]["current_selection"]["selection_reason"] == "explicit_override"


def test_preview_unknown_workflow_is_404(client, stored_psop, cards, resolution_inputs):
    response = client.post(f"{BASE}/role-execution/preview",
                           json={"psop_id": "missing", "scope": "t/city-a/b"})
    assert response.status_code == 404


def test_preview_non_role_workflow_is_422(client, monkeypatch, cards, resolution_inputs):
    plain = _plain_psop()
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        get_psop_by_id=lambda _: plain))
    response = client.post(f"{BASE}/role-execution/preview",
                           json={"psop_id": plain.id, "scope": "t/city-a/b"})
    assert response.status_code == 422


def test_preview_requires_an_authenticated_caller(monkeypatch, stored_psop, cards,
                                                  resolution_inputs):
    import hashlib

    from orchestrate.server import auth

    monkeypatch.setattr(auth, "get_conf", lambda: {
        "persistence_mode": "file", "enable_https": "false",
        "access_password": hashlib.sha256(b"SyntheticBusiness9!").hexdigest()})
    monkeypatch.setattr(auth, "current_context", lambda: SimpleNamespace(
        has_users=True, users=SimpleNamespace(has_any=lambda: True)))
    monkeypatch.setattr(auth, "_session_store", auth._SessionStore())
    monkeypatch.setattr(auth, "_pending_password_change", set())
    with TestClient(app) as anonymous:
        response = anonymous.post(f"{BASE}/role-execution/preview",
                                  json={"psop_id": stored_psop.id, "scope": "t/city-a/b"})
    assert response.status_code == 401


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# POST /role-execution/execute 鈥?confirmed dispatch (P2)
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
class _CapturingClient:
    def __init__(self, contents):
        self._contents = contents

    async def stream_message(self, agent_name, content):
        self._contents.append(content)
        from workflow_engine import A2AStreamEvent
        yield A2AStreamEvent(event_type="task", task_state="TASK_STATE_COMPLETED", metadata={})

    async def close(self):
        pass


@pytest.fixture
def fake_engine(monkeypatch):
    contents = []

    def _fake_client(self):
        return _CapturingClient(contents)

    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", "test-only-role-dispatch-key-32-bytes")
    monkeypatch.setattr("orchestrate.runtime.exec_engine.OrchestrationEngine._get_engine_client",
                        _fake_client)
    return contents


@pytest.fixture
def saved_records(monkeypatch):
    from common.custom.interface_type import InterfaceType

    records = []

    class _FakeHandler:
        def handle(self, record):
            records.append(record)
            return record

    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler",
                        lambda interface_type: _FakeHandler())
    assert InterfaceType.SAVE_EXECUTION_RECORD is not None
    return records


def test_execute_without_confirmation_is_rejected(client, stored_psop, cards, resolution_inputs):
    response = client.post(f"{BASE}/role-execution/execute",
                           json={"psop_id": stored_psop.id, "scope": "t/city-a/b"})
    assert response.status_code == 422


def test_execute_on_closed_deployment_refuses_with_evidence(client, stored_psop, cards,
                                                            resolution_inputs, saved_records,
                                                            monkeypatch):
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_role_execution_mode",
                        lambda: None)
    response = client.post(f"{BASE}/role-execution/execute", json={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "confirm_fingerprint": "0" * 64,
    })

    assert response.status_code == 200
    assert "ROLE_EXECUTION_NOT_ENABLED" in response.text
    assert len(saved_records) == 1
    record = saved_records[0]
    assert record.status == ExecutionStatus.FAILED
    assert record.confirm_fingerprint == "0" * 64


def test_execute_confirmed_mismatch_fails_with_evidence(client, stored_psop, cards,
                                                        resolution_inputs, saved_records):
    response = client.post(f"{BASE}/role-execution/execute", json={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "task_overrides": {"t1": "inst-a"},
        "confirm_fingerprint": "0" * 64,
    })

    assert response.status_code == 200
    assert "RESOLUTION_MISMATCH" in response.text
    assert len(saved_records) == 1
    record = saved_records[0]
    assert record.status == ExecutionStatus.FAILED
    assert record.confirm_fingerprint == "0" * 64
    assert record.overrides_applied["task_overrides"] == {"t1": "inst-a"}


def test_execute_confirmed_dispatch_keeps_fingerprint(client, stored_psop, cards,
                                                      resolution_inputs, fake_engine,
                                                      saved_records):
    preview = client.post(f"{BASE}/role-execution/preview",
                          json={"psop_id": stored_psop.id, "scope": "t/city-a/b"}).json()["data"]
    digest = preview["resolution_fingerprint"]

    response = client.post(f"{BASE}/role-execution/execute", json={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "confirm_fingerprint": digest,
    })

    assert response.status_code == 200
    events = [json.loads(line[len("data: "):]) for line in response.text.splitlines()
              if line.startswith("data: ")]
    assert any(event.get("type") == "resolution" for event in events)
    assert len(saved_records) == 1
    record = saved_records[0]
    assert record.status == ExecutionStatus.SUCCESS
    assert record.confirm_fingerprint == digest
    assert record.overrides_applied is None
    assert fake_engine, "dispatch payload captured"


def test_legacy_get_execute_applies_override_query(client, stored_psop, cards,
                                                   resolution_inputs, fake_engine,
                                                   saved_records):
    response = client.get(f"{BASE}/execute", params={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "task_overrides": json.dumps({"t1": "inst-a"}),
        "tie_break": "instance_id",
    })

    assert response.status_code == 200
    assert len(saved_records) == 1
    record = saved_records[0]
    assert record.status == ExecutionStatus.SUCCESS
    assert record.overrides_applied == {
        "task_overrides": {"t1": "inst-a"},
        "group_overrides": {},
        "tie_break": "instance_id",
    }
    assert record.confirm_fingerprint is None


def test_legacy_get_execute_rejects_bad_override_json(client, stored_psop, cards,
                                                      resolution_inputs):
    response = client.get(f"{BASE}/execute", params={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "task_overrides": "{not-json",
    })
    assert response.status_code == 400


def test_legacy_get_execute_rejects_bad_tie_break(client, stored_psop, cards,
                                                  resolution_inputs):
    response = client.get(f"{BASE}/execute", params={
        "psop_id": stored_psop.id, "scope": "t/city-a/b",
        "tie_break": "loudest",
    })
    assert response.status_code == 400
