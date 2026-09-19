import asyncio
from types import SimpleNamespace

import pytest
from a2a.types import TaskState
from samples.agents.host_execution import (
    HostExecutionTracker,
    host_event_state,
    host_final_state,
)
from host_agent.runtime import HostAgentExecutor


def test_close_is_not_mapped_to_a_terminal_task_state():
    assert host_event_state("complete") is TaskState.TASK_STATE_COMPLETED
    assert host_event_state("error") is TaskState.TASK_STATE_FAILED
    assert host_event_state("close") is TaskState.TASK_STATE_WORKING


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ([{"type": "start"}, {"type": "complete"}, {"type": "close"}], TaskState.TASK_STATE_COMPLETED),
        ([{"type": "start"}, {"type": "error"}, {"type": "close"}], TaskState.TASK_STATE_FAILED),
        ([], TaskState.TASK_STATE_FAILED),
    ],
)
def test_final_task_state_follows_workflow_outcome(events, expected):
    assert host_final_state(events) is expected


def test_workbench_close_event_stays_working_until_terminal_task():
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    context = SimpleNamespace(task_id="task-1", context_id="context-1")

    event = executor._event_to_task_update({"type": "close", "data": {}}, context, "en")

    assert event.status.state is TaskState.TASK_STATE_WORKING


@pytest.mark.asyncio
async def test_tracker_cancels_the_active_execution_task():
    tracker = HostExecutionTracker()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def execution():
        tracker.begin("task-1")
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        finally:
            tracker.end("task-1")

    task = asyncio.create_task(execution())
    await started.wait()

    assert tracker.cancel("task-1") is True
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled.is_set()
    assert tracker.cancel("task-1") is False
