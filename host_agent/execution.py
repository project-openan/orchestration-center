from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from a2a.types import TaskState


class HostExecutionTracker:
    """Track the asyncio task behind each active host-agent execution."""

    def __init__(self) -> None:
        self._executions: dict[str, asyncio.Task] = {}

    def begin(self, task_id: str) -> None:
        current = asyncio.current_task()
        if current is None:
            raise RuntimeError("Host-agent execution must run inside an asyncio task")
        self._executions[task_id] = current

    def end(self, task_id: str) -> None:
        current = asyncio.current_task()
        if self._executions.get(task_id) is current:
            del self._executions[task_id]

    def cancel(self, task_id: str) -> bool:
        execution = self._executions.get(task_id)
        if execution is None or execution.done():
            return False
        execution.cancel()
        return True


def host_event_state(event_type: str) -> TaskState:
    """Map a workflow event to an A2A task state."""
    if event_type == "complete":
        return TaskState.TASK_STATE_COMPLETED
    if event_type == "error":
        return TaskState.TASK_STATE_FAILED
    return TaskState.TASK_STATE_WORKING


def host_final_state(events: Iterable[dict[str, Any]]) -> TaskState:
    """Derive the terminal task state from collected workflow events."""
    for event in reversed(list(events)):
        event_type = event.get("type")
        if event_type == "error":
            return TaskState.TASK_STATE_FAILED
        if event_type == "complete":
            return TaskState.TASK_STATE_COMPLETED
    return TaskState.TASK_STATE_FAILED
