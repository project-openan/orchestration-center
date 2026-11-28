# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from workflow_engine import A2AStreamEvent

from orchestrate.core.model.psop import PSOP
from orchestrate.runtime.exec_engine import OrchestrationEngine
from orchestrate.core.shared_handlers import SharedHandlers


class _EmptyRetrieval:
    def retrieve_psop_by_intent_topn(self, intent, limit):
        del intent, limit
        return []


def test_compatibility_dispatch_selects_the_registered_agent_by_name(monkeypatch):
    """The host is the agent the PSOP's SelfLoop tasks name; a center-only skill is not a marker."""
    worker = SimpleNamespace(name="Domain Worker", skills=[SimpleNamespace(id="diagnose", tags=[])])
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {})
    transport = MagicMock()
    monkeypatch.setattr("orchestrate.runtime.exec_engine.A2ATransport", transport)
    engine = OrchestrationEngine([worker], target_agent="Domain Worker", select_template=False)

    engine._get_engine_client("Domain Worker")

    transport.assert_called_once()
    assert transport.call_args.kwargs["agent_cards"] == [worker]


def test_psops_with_an_empty_id_do_not_share_task_ids():
    template = {
        "id": "", "name": "Legacy",
        "steps": [{"name": "local", "type": "SelfLoop", "subtasks": [
            {"agent": "Host Agent", "description": "Summarize", "skill": "summarize"},
        ]}],
    }
    first = PSOP.model_validate(template)
    second = PSOP.model_validate(template)
    assert first.steps[0].subtasks[0].task_id != second.steps[0].subtasks[0].task_id


def test_psop_workflow_host_prefers_the_declaration_over_selfloop_agents():
    psop = PSOP(name="Explicit Host", workflow_host="Approved Host", steps=[])
    assert psop.workflow_host_name() == "Approved Host"
    psop = PSOP.model_validate({
        "name": "Conflicting Host", "workflow_host": "Approved Host",
        "steps": [{"name": "local", "type": "SelfLoop", "subtasks": [
            {"agent": "Different Host", "description": "Summarize", "skill": "summarize"},
        ]}],
    })
    assert psop.workflow_host_name() == "Approved Host"


def test_psop_workflow_host_keeps_a_legacy_single_selfloop_agent():
    psop = PSOP.model_validate({
        "name": "Legacy",
        "steps": [{"name": "local", "type": "SelfLoop", "subtasks": [
            {"agent": "Host Agent", "description": "Summarize", "skill": "summarize"},
        ]}],
    })
    assert psop.workflow_host_name() == "Host Agent"


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_same_name_hosts_require_an_unambiguous_organization(monkeypatch, reverse):
    cards = [
        SimpleNamespace(name="Host Agent", provider=SimpleNamespace(organization=org))
        for org in ("Org-A", "Org-B")
    ]
    if reverse:
        cards.reverse()
    config = {}
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: config)
    engine = OrchestrationEngine(cards, select_template=False)
    events = [event async for event in engine.events("diagnose service")]
    assert events[-1]["data"]["code"] == "HOST_AGENT_AMBIGUOUS"

    config["workflow_host_agent_organization"] = "Org-B"
    engine = OrchestrationEngine(cards, select_template=False)
    assert engine._find_target_card().provider.organization == "Org-B"


class _PublicWorkflowClient:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def stream_message(self, agent_name, content):
        self.sent.append((agent_name, content))
        yield A2AStreamEvent(
            event_type="status_update",
            task_id="task-1",
            context_id="context-1",
            task_state="TASK_STATE_WORKING",
            metadata={
                "__sdk_event__": json.dumps({
                    "type": "task_status_changed",
                    "data": {"status": "running"},
                })
            },
        )

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_orchestration_uses_public_workflow_stream_api(monkeypatch):
    client = _PublicWorkflowClient()
    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine._select_template = False
    engine.lang = "zh"
    engine._agent_cards = [SimpleNamespace(name="Host Agent")]
    engine._target_agent = "Host Agent"
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda target=None: client)

    events = [event async for event in engine.events("diagnose service")]

    assert any(
        event == {"type": "task_status_changed", "data": {"status": "running"}}
        for event in events
    )
    assert events
    assert any(event["type"] == "start" and event["data"].get("target_agent") == "Host Agent"
               for event in events)
    assert client.sent[0][0] == "Host Agent"
    assert client.sent[0][1].parts[0].text == "diagnose service"
    assert client.closed


@pytest.mark.asyncio
async def test_orchestration_reports_terminal_cancellation_without_sdk_metadata(monkeypatch):
    class _CancelledClient(_PublicWorkflowClient):
        async def stream_message(self, agent_name, content):
            yield A2AStreamEvent(
                event_type="status_update",
                task_id="task-1",
                context_id="context-1",
                task_state="TASK_STATE_CANCELED",
                metadata={},
            )

    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine._select_template = False
    engine.lang = "zh"
    engine._target_agent = "Host Agent"
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda target=None: _CancelledClient())

    events = [event async for event in engine.events("diagnose service")]
    assert events[-1]["type"] == "cancelled"


@pytest.mark.asyncio
async def test_orchestration_reports_a2a_completion_without_sdk_metadata(monkeypatch):
    class _CompletedClient(_PublicWorkflowClient):
        async def stream_message(self, agent_name, content):
            yield A2AStreamEvent(
                event_type="status_update",
                task_id="task-1",
                context_id="context-1",
                task_state="TASK_STATE_COMPLETED",
                metadata={},
            )

    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine._select_template = False
    engine.lang = "zh"
    engine._target_agent = "Host Agent"
    engine._select_template = False
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda target=None: _CompletedClient())

    events = [event async for event in engine.events("diagnose service")]
    assert events[-1]["type"] == "complete"
    assert all(event["type"] != "error" for event in events)


@pytest.mark.asyncio
async def test_dispatch_survives_a_broken_reporting_proof(monkeypatch):
    from uuid import uuid4

    class _CompletedClient(_PublicWorkflowClient):
        async def stream_message(self, agent_name, content):
            yield A2AStreamEvent(
                event_type="status_update",
                task_id="task-1",
                context_id="context-1",
                task_state="TASK_STATE_COMPLETED",
                metadata={},
            )

    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine.lang = "zh"
    engine._target_agent = "Host Agent"
    engine._select_template = False
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda target=None: _CompletedClient())
    # A too-short reporting key makes the proof signer raise; the run must still dispatch.
    monkeypatch.setenv("OPENAN_CENTER_DISPATCH_KEY", "too-short")

    events = [event async for event in engine.events("diagnose service", execution_id=str(uuid4()))]
    assert events[-1]["type"] == "complete"
    assert all(event["type"] != "error" for event in events)


def test_orchestration_does_not_load_sample_credentials_implicitly(monkeypatch):
    monkeypatch.delenv("ORCH_AGENT_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {})
    engine = OrchestrationEngine([], target_agent="Host Agent")
    assert engine._cred_path is None
    assert engine._ssl_verify is True
