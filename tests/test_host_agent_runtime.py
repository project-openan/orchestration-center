# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from collections import OrderedDict
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from a2a.types import TaskState
from workflow_engine import MessageContent, StubWorkflowEngineClient

from host_agent.center_dispatch import KEY_ENV, write_center_dispatch_proof
from host_agent.config import HostAgentConfig
from host_agent.execution import HostExecutionTracker
from host_agent.runtime import HostAgentExecutor


class _EventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def _workflow():
    from workflow_engine import JumpCondition, Task, Workflow, WorkflowStep

    return Workflow(
        id="wf-1",
        name="baseline workflow",
        steps=[
            WorkflowStep(
                name="step_1",
                subtasks=[Task(agent="stub-agent", description="Run stub task")],
                next=[JumpCondition(step="endNode")],
            )
        ],
    )


def _executor():
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._execution_reporter = None
    executor._seen_center_dispatches = OrderedDict()
    executor._execution_tracker = HostExecutionTracker()
    executor._config = HostAgentConfig(
        orchestration_url="https://orch.test",
        registry_url="https://registry.test",
    )
    executor._extension_lifecycle = None
    executor._workflow_repository = SimpleNamespace(
        get=AsyncMock(),
        find=AsyncMock(),
    )
    return executor


def test_center_dispatch_claim_survives_a_restart(tmp_path, monkeypatch):
    from host_agent.center_dispatch import CLAIMS_VARIABLE

    monkeypatch.setenv(CLAIMS_VARIABLE, str(tmp_path / "claims.json"))
    execution_id = str(uuid4())

    first = _executor()
    first._claim_center_dispatch(execution_id)

    restarted = _executor()
    with pytest.raises(ValueError, match="already received"):
        restarted._claim_center_dispatch(execution_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", ["none", "tampered", "valid", "unsigned_snapshot"])
async def test_only_authenticated_center_dispatch_uses_center_history(monkeypatch, proof):
    executor = _executor()
    executor._execution_reporter = object()
    executor._workflow_repository.find.return_value = _workflow()
    executor._load_agent_cards = AsyncMock(return_value=[])
    executor._engine_client_factory = SimpleNamespace(create=lambda _: StubWorkflowEngineClient())
    executor._control_point_factory = lambda _: None
    context = _context_snapshot() if proof == "unsigned_snapshot" else _context()
    context.metadata["__orch_legacy_proxy__"] = True
    monkeypatch.setenv(KEY_ENV, "synthetic-center-test-key-32-bytes")
    if proof in {"tampered", "valid"}:
        write_center_dispatch_proof(context.metadata, execution_id=str(uuid4()), intent=context.get_user_input())
    if proof == "tampered":
        context.get_user_input = lambda: "modified intent"
    invocations = []

    async def execute_psop(**kwargs):
        invocations.append(kwargs)
        yield {"type": "complete", "data": {"status": "success"}}

    monkeypatch.setattr("host_agent.runtime.execute_psop", execute_psop)
    queue = _EventQueue()
    await executor.execute(context, queue)

    if proof == "unsigned_snapshot":
        assert not invocations
        assert queue.events[-1].status.state is TaskState.TASK_STATE_FAILED
        return
    assert len(invocations) == 1
    assert invocations[0].get("reporter") is (None if proof == "valid" else executor._execution_reporter)
    if proof == "valid":
        await executor.execute(context, _EventQueue())
        assert len(invocations) == 1


def _context(psop_id=None):
    metadata = {"__orch_psop_id__": psop_id} if psop_id else {}
    return SimpleNamespace(
        task_id="task-1",
        context_id="context-1",
        metadata=metadata,
        message=None,
        get_user_input=lambda: "run workflow",
    )


def _context_snapshot():
    snapshot = {
        "id": "wf-1",
        "name": "baseline workflow",
        "steps": [
            {
                "name": "step_1",
                "subtasks": [{"agent": "stub-agent", "description": "Run stub task"}],
                "next": [{"step": "endNode"}],
            }
        ],
    }
    return SimpleNamespace(
        task_id="task-1",
        context_id="context-1",
        metadata={"__orch_psop__": snapshot},
        message=None,
        get_user_input=lambda: "run workflow",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["binding_metadata", "raw_role"])
async def test_role_execution_remains_disabled_until_host_verification(mode):
    executor = _executor()
    context = _context_snapshot()
    if mode == "binding_metadata":
        context.metadata["__orch_binding__"] = "{}"
    else:
        context.metadata["__orch_psop__"]["steps"][0]["subtasks"][0]["binding"] = "role"
    executor._load_agent_cards = AsyncMock()
    queue = _EventQueue()
    await executor.execute(context, queue)
    executor._load_agent_cards.assert_not_awaited()
    errors = [event for event in queue.events if event.status.state == TaskState.TASK_STATE_FAILED]
    assert errors
    assert "ROLE_EXECUTION_NOT_ENABLED" in str(errors[-1])


def test_runtime_requires_a_control_point_factory():
    with pytest.raises(ValueError, match="control_point_factory is required"):
        HostAgentExecutor(
            config=HostAgentConfig(
                orchestration_url="https://orch.test",
                registry_url="https://registry.test",
            ),
            control_point_factory=None,
        )


@pytest.mark.asyncio
async def test_runtime_accepts_an_injected_control_point(monkeypatch):
    executor = _executor()

    class _InjectedControlPoint:
        async def on_task(self, request):
            return MessageContent.text("injected policy")

    executor._control_point_factory = _InjectedControlPoint
    assert isinstance(executor._control_point_factory, type)


@pytest.mark.asyncio
async def test_execute_uses_explicit_psop_id_and_wraps_sdk_events(monkeypatch):
    executor = _executor()
    queue = _EventQueue()
    loaded_ids = []

    async def get_psop(psop_id):
        loaded_ids.append(psop_id)
        workflow = _workflow()
        workflow.id = psop_id
        return workflow

    async def load_agent_cards():
        return [SimpleNamespace(name="stub-agent")]

    async def find_psop(intent):
        raise AssertionError("explicit psop_id must not trigger intent search")

    async def process_intent(intent):
        return intent

    monkeypatch.setattr(executor, "_process_intent", process_intent)
    executor._workflow_repository.get = get_psop
    executor._workflow_repository.find = find_psop
    monkeypatch.setattr(executor, "_load_agent_cards", load_agent_cards)

    executor._engine_client_factory = SimpleNamespace(
        create=lambda agent_cards: StubWorkflowEngineClient()
    )

    class _ExplicitControlPoint:
        def __init__(self, *args, **kwargs):
            pass

        async def on_task(self, request):
            return MessageContent.text("stub task content")

    executor._control_point_factory = _ExplicitControlPoint
    await executor.execute(_context("wf-explicit"), queue)

    assert loaded_ids == ["wf-explicit"]
    sdk_events = [json.loads(event.metadata["__sdk_event__"]) for event in queue.events if hasattr(event, "metadata") and "__sdk_event__" in event.metadata]
    assert [event["type"] for event in sdk_events][:2] == ["start", "step_start"]
    terminal = queue.events[-1]
    assert terminal.status.state in {TaskState.TASK_STATE_COMPLETED, TaskState.TASK_STATE_FAILED}
    assert queue.events[-1].status.state is TaskState.TASK_STATE_COMPLETED


@pytest.mark.asyncio
async def test_sdk_events_remain_wrapped_through_stub_engine(monkeypatch):
    executor = _executor()
    queue = _EventQueue()
    stub_client = StubWorkflowEngineClient()

    async def find_psop(intent):
        return _workflow()

    async def load_agent_cards():
        return [SimpleNamespace(name="stub-agent")]

    async def process_intent(intent):
        return intent

    monkeypatch.setattr(executor, "_process_intent", process_intent)
    monkeypatch.setattr(executor, "_load_agent_cards", load_agent_cards)
    executor._workflow_repository.find = find_psop

    class _ExplicitControlPoint:
        def __init__(self, *args, **kwargs):
            pass

        async def on_task(self, request):
            return MessageContent.text("stub task content")

    executor._engine_client_factory = SimpleNamespace(create=lambda agent_cards: stub_client)
    executor._control_point_factory = _ExplicitControlPoint
    await executor.execute(_context(), queue)

    wrapped = [
        json.loads(event.metadata["__sdk_event__"])
        for event in queue.events
        if hasattr(event, "metadata") and "__sdk_event__" in event.metadata
    ]
    assert "step_start" in [event["type"] for event in wrapped]
    assert "step_complete" in [event["type"] for event in wrapped]


@pytest.mark.asyncio
async def test_execute_prefers_psop_snapshot_from_orchestration(monkeypatch):
    executor = _executor()
    queue = _EventQueue()

    async def fail_repository(*args, **kwargs):
        raise AssertionError("snapshot must not trigger workflow repository")

    async def load_agent_cards():
        return [SimpleNamespace(name="stub-agent")]

    async def process_intent(intent):
        return intent

    executor._workflow_repository.get = fail_repository
    executor._workflow_repository.find = fail_repository
    monkeypatch.setattr(executor, "_process_intent", process_intent)
    monkeypatch.setattr(executor, "_load_agent_cards", load_agent_cards)
    executor._engine_client_factory = SimpleNamespace(
        create=lambda agent_cards: StubWorkflowEngineClient()
    )

    class _ControlPoint:
        def __init__(self, *args, **kwargs):
            pass

        async def on_task(self, request):
            return MessageContent.text("stub task content")

    executor._control_point_factory = _ControlPoint
    context = _context_snapshot()
    monkeypatch.setenv(KEY_ENV, "synthetic-center-test-key-32-bytes")
    write_center_dispatch_proof(context.metadata, execution_id=str(uuid4()), intent=context.get_user_input())
    await executor.execute(context, queue)

    wrapped = [
        json.loads(event.metadata["__sdk_event__"])
        for event in queue.events
        if hasattr(event, "metadata") and "__sdk_event__" in event.metadata
    ]
    assert [event["type"] for event in wrapped][:2] == ["start", "step_start"]


def test_event_update_preserves_raw_sdk_event():
    executor = _executor()
    context = SimpleNamespace(task_id="task-1", context_id="context-1")
    raw = {"type": "task_status_changed", "data": {"status": "success"}}

    update = executor._event_to_task_update(raw, context, "zh")

    assert json.loads(update.metadata["__sdk_event__"]) == raw
    assert update.status.state is TaskState.TASK_STATE_WORKING


def test_close_event_does_not_mark_task_terminal():
    executor = _executor()
    context = SimpleNamespace(task_id="task-1", context_id="context-1")

    update = executor._event_to_task_update({"type": "close", "data": {}}, context, "en")

    assert update.status.state is TaskState.TASK_STATE_WORKING
