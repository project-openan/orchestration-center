# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""events() role-resolution integration: resolution event, dispatch metadata, errors."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrate.core.model.instance_binding import (
    InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.runtime.exec_engine import _resolution_error_event
from orchestrate.runtime.instance_projection import ResolutionRequest
from samples.role_pilot.technical_server import pilot_card
from workflow_engine import A2AStreamEvent

SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
OPTIMIZER = "ran-energy-optimizer"


@pytest.fixture(autouse=True)
def server_authorization(monkeypatch):
    monkeypatch.delenv("ORCH_ROLE_DISPATCH_KEY", raising=False)
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                        lambda: ["inst-a", "inst-b"])


class _CapturingClient:
    def __init__(self):
        self.contents = []

    async def stream_message(self, agent_name, content):
        self.contents.append(content)
        yield A2AStreamEvent(event_type="task", task_state="TASK_STATE_COMPLETED", metadata={})

    async def close(self):
        pass


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
    scope = ServiceScope(tenant="t", site="s", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
        InstanceBinding(
            instance_id="inst-b", agent_name="Technical RAN B", endpoint="http://127.0.0.1:2",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="fulfill-energy-intent",
                                 instance_skill_id="explore-b", execution_skill="Explore B")],
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


def _engine(monkeypatch, cards, client):
    from orchestrate.runtime.exec_engine import OrchestrationEngine

    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine._agent_cards = cards
    engine._target_agent = "Host Agent"
    monkeypatch.setattr(engine, "_get_engine_client", lambda: client)
    return engine


async def _collect(engine, intent, **kwargs):
    return [event async for event in engine.events(intent, **kwargs)]


@pytest.mark.asyncio
async def test_events_freezes_role_psop_but_blocks_dispatch_without_trust_key(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    client = _CapturingClient()
    engine = _engine(monkeypatch, [pilot_card("a", 1), pilot_card("b", 2)], client)
    psop = _role_psop()
    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])

    events = await _collect(engine, "explore", psop=psop, resolution_request=request)

    resolution_events = [e for e in events if e["type"] == "resolution"]
    assert len(resolution_events) == 1
    data = resolution_events[0]["data"]
    assert data["catalog_version"] == "pilot-wireless-v1"
    assert data["execution_scope"] == "t/s/b"
    assert data["execution_id"]
    assert data["bindings"]
    assert data["card_fingerprints"]
    # Only inst-a satisfies the explore skill, so selection is pinned.
    assert data["bindings"][0]["instance_id"] == "inst-a"

    psop_updates = [e for e in events if e["type"] == "psop_update"]
    final_psop = psop_updates[-1]["data"]["psop"]
    assert all(task["binding"] == "instance"
               for step in final_psop["steps"] for task in step["subtasks"])
    assert final_psop["catalog_version"] is None

    # Resolution evidence precedes the execution-copy projection.
    resolution_index = events.index(resolution_events[0])
    last_psop_update_index = max(
        index for index, event in enumerate(events) if event["type"] == "psop_update")
    assert resolution_index < last_psop_update_index

    assert client.contents == []
    assert events[-1]["data"]["code"] == "ROLE_EXECUTION_NOT_ENABLED"
    from orchestrate.runtime.exec_engine import _role_dispatch_metadata
    from orchestrate.core.model.role_execution_snapshot import RoleExecutionSnapshot
    snapshot = RoleExecutionSnapshot.model_validate(data["resolution_snapshot"])
    metadata = _role_dispatch_metadata(snapshot)
    binding = json.loads(metadata["__orch_binding__"])
    assert binding["config_version"] == "cfg-v1"
    assert binding["catalog_version"] == "pilot-wireless-v1"
    assert binding["policy_version"] == "policy-v1"
    # Scope travels in the unified tenant/site/business_object string form.
    assert binding["scope"] == "t/s/b"
    assert binding["bindings"]
    # Future dispatch metadata is derived from the frozen execution copy.
    execution_copy = snapshot.execution_psop.model_dump(mode="json")
    assert execution_copy["steps"][0]["subtasks"][0]["binding"] == "instance"
    assert execution_copy == final_psop
    cards = json.loads(metadata["__orch_cards__"])
    assert cards["cards"]
    assert cards["execution_id"] == data["execution_id"]
    assert snapshot.template.id == psop.id


@pytest.mark.asyncio
async def test_events_resolution_failure_yields_structured_error_without_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: None)
    client = _CapturingClient()
    engine = _engine(monkeypatch, [], client)

    events = await _collect(engine, "explore", psop=_role_psop(),
                            resolution_request=ResolutionRequest(scope="t/s/b"))

    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["data"]["code"] == "RESOLUTION_INPUT_INVALID"
    assert client.contents == []


@pytest.mark.asyncio
async def test_events_catalog_unavailable_error(monkeypatch):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: None)
    client = _CapturingClient()
    engine = _engine(monkeypatch, [], client)

    events = await _collect(engine, "explore", psop=_role_psop(),
                            resolution_request=ResolutionRequest(scope="t/s/b"))

    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["data"]["code"] == "CATALOG_VERSION_UNAVAILABLE"
    assert client.contents == []


@pytest.mark.asyncio
async def test_events_without_role_tasks_unchanged(monkeypatch):
    client = _CapturingClient()
    engine = _engine(monkeypatch, [], client)

    events = await _collect(engine, "do work", psop=_plain_psop())

    assert all(e["type"] != "resolution" for e in events)
    assert len(client.contents) == 1
    metadata = client.contents[0].metadata
    assert "__orch_binding__" not in metadata
    assert "__orch_cards__" not in metadata
    assert metadata["__orch_psop_id__"] == "wf-plain"


def test_resolution_error_event_code_fallback():
    """Plain ValueError text must not leak as the error code; only an
    ALL_CAPS message prefix is trusted, anything else is RESOLUTION_FAILED."""
    masked = _resolution_error_event(ValueError("frozen envelope broke: detail"))
    assert masked["data"]["code"] == "RESOLUTION_FAILED"
    assert "frozen envelope broke" in masked["data"]["error"]
    prefix = _resolution_error_event(ValueError("ROLE_EXECUTION_NOT_ENABLED: unresolved"))
    assert prefix["data"]["code"] == "ROLE_EXECUTION_NOT_ENABLED"
    bare = _resolution_error_event(ValueError("something exploded"))
    assert bare["data"]["code"] == "RESOLUTION_FAILED"


@pytest.mark.asyncio
async def test_events_intent_search_resolves_role_template(monkeypatch, tmp_path):
    """psop=None: the intent-retrieved role template is resolved inside
    events() and the execution copy is dispatched."""
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    client = _CapturingClient()
    engine = _engine(monkeypatch, [pilot_card("a", 1), pilot_card("b", 2)], client)
    psop = _role_psop()
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        retrieve_psop_by_intent_topn=lambda *args: [
            SimpleNamespace(workflow_id=psop.id, name=psop.name)
        ],
        get_psop_by_id=lambda _: psop,
    ))
    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])

    events = await _collect(engine, "explore energy", psop=None, resolution_request=request)

    resolution_events = [e for e in events if e["type"] == "resolution"]
    assert len(resolution_events) == 1
    assert resolution_events[0]["data"]["catalog_version"] == "pilot-wireless-v1"
    psop_updates = [e for e in events if e["type"] == "psop_update"]
    assert all(task["binding"] == "instance"
               for step in psop_updates[-1]["data"]["psop"]["steps"]
               for task in step["subtasks"])
    assert client.contents == []
    assert events[-1]["data"]["code"] == "ROLE_EXECUTION_NOT_ENABLED"


@pytest.mark.asyncio
@pytest.mark.parametrize("results", [[], [SimpleNamespace(workflow_id="missing", name="Missing")]])
async def test_auto_execution_never_falls_back_when_template_missing(monkeypatch, results):
    client = _CapturingClient()
    engine = _engine(monkeypatch, [], client)
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        retrieve_psop_by_intent_topn=lambda *args: results,
        get_psop_by_id=lambda _: None,
    ))
    events = await _collect(engine, "unknown")
    assert events[-1]["data"]["code"] == "PSOP_NOT_FOUND"
    assert client.contents == []


def test_resolution_failure_preserves_candidates():
    from orchestrate.runtime.role_resolver import ResolutionError
    event = _resolution_error_event(ResolutionError("AMBIGUOUS_BINDING", "Ambiguous", candidates=["a", "b"]))
    assert event["data"]["candidates"] == ["a", "b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("by_intent", [False, True])
async def test_role_dispatch_with_trusted_envelope(monkeypatch, tmp_path, by_intent):
    from host_agent.dispatch_auth import verify_dispatch
    key = "synthetic-test-key-for-role-dispatch-only"
    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", key)
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    template = _role_psop()
    original = template.model_dump_json()
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        retrieve_psop_by_intent_topn=lambda *args: [SimpleNamespace(workflow_id=template.id, name=template.name)],
        get_psop_by_id=lambda _: template,
    ))
    client = _CapturingClient()
    engine = _engine(monkeypatch, [pilot_card("a", 1), pilot_card("b", 2)], client)
    events = await _collect(engine, "explore", psop=None if by_intent else template,
                            resolution_request=ResolutionRequest(scope="t/s/b"))
    assert not [event for event in events if event["type"] == "error"]
    assert events[-1]["type"] == "complete"
    assert len(client.contents) == 1
    verify_dispatch(client.contents[0].metadata, key, intent="explore")
    assert template.model_dump_json() == original
