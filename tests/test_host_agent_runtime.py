import json
from types import SimpleNamespace

import pytest
from a2a.types import TaskState
from unittest.mock import AsyncMock
from workflow_engine import MessageContent, StubWorkflowEngineClient

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
    executor._execution_tracker = HostExecutionTracker()
    executor._ssl_verify = False
    executor._orch_url = "https://orch.test"
    executor._registry_url = "https://registry.test"
    executor._credentials_config = "credentials.json"
    executor._extension_lifecycle = None
    executor._workflow_repository = SimpleNamespace(
        get=AsyncMock(),
        find=AsyncMock(),
    )
    return executor


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


def test_runtime_requires_a_control_point_factory():
    with pytest.raises(ValueError, match="control_point_factory is required"):
        HostAgentExecutor(extension_agent_cards=[])


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
        return _workflow()

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

    from host_agent import runtime as module

    monkeypatch.setattr(
        module,
        "A2ATransport",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        module,
        "WorkflowEngineClient",
        SimpleNamespace(owning=lambda transport, **kwargs: StubWorkflowEngineClient()),
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

    from host_agent import runtime as module

    monkeypatch.setattr(
        module,
        "A2ATransport",
        lambda *args, **kwargs: SimpleNamespace(),
    )

    class _ExplicitControlPoint:
        def __init__(self, *args, **kwargs):
            pass

        async def on_task(self, request):
            return MessageContent.text("stub task content")

    monkeypatch.setattr(module, "WorkflowEngineClient", SimpleNamespace(owning=lambda transport, **kwargs: stub_client))
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
    monkeypatch.setattr(
        "host_agent.runtime.A2ATransport",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "host_agent.runtime.WorkflowEngineClient",
        SimpleNamespace(owning=lambda transport, **kwargs: StubWorkflowEngineClient()),
    )

    class _ControlPoint:
        def __init__(self, *args, **kwargs):
            pass

        async def on_task(self, request):
            return MessageContent.text("stub task content")

    executor._control_point_factory = _ControlPoint
    await executor.execute(_context_snapshot(), queue)

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
