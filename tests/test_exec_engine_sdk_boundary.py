# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace

import pytest
from workflow_engine import A2AStreamEvent

from orchestrate.runtime.exec_engine import OrchestrationEngine
from orchestrate.server.shared_handlers import SharedHandlers


class _EmptyRetrieval:
    def retrieve_psop_by_intent_topn(self, intent, limit):
        del intent, limit
        return []


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
    engine.lang = "zh"
    engine._agent_cards = [SimpleNamespace(name="Host Agent")]
    engine._target_agent = "Host Agent"
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda: client)

    events = [event async for event in engine.events("diagnose service")]

    assert events[-1] == {
        "type": "task_status_changed",
        "data": {"status": "running"},
    }
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
    engine.lang = "zh"
    engine._target_agent = "Host Agent"
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda: _CancelledClient())

    events = [event async for event in engine.events("diagnose service")]
    assert events[-1]["type"] == "cancelled"


@pytest.mark.asyncio
async def test_orchestration_reports_terminal_success_without_sdk_metadata(monkeypatch):
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
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: _EmptyRetrieval())
    monkeypatch.setattr(engine, "_get_engine_client", lambda: _CompletedClient())

    events = [event async for event in engine.events("diagnose service")]
    assert [event["type"] for event in events].count("complete") == 1


def test_orchestration_does_not_load_sample_credentials_implicitly(monkeypatch):
    monkeypatch.delenv("ORCH_AGENT_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {})
    engine = OrchestrationEngine([], target_agent="Host Agent")
    assert engine._cred_path is None
    assert engine._ssl_verify is True
