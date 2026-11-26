# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Bridge SDK callback IDs to verified PSOP positions using public events."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from loguru import logger
from workflow_engine import (
    BusinessFailure, ControlPoint, EventType, MessageContent, NegotiationReply,
    NegotiationRequest, RouteDecision, RouteRequest, TaskRequest, TaskResult,
)

from host_agent.config import RoleExecutionContext, RoleTaskIdentity


class RoleExecutionBridge:
    """One execution's mapping, populated by the runner's public on_event hook.

    TASK_REQUEST supplies the exact step/subtask position before the SDK invokes
    a policy. The runner drains events asynchronously, so policy callbacks wait
    for registration. No SDK UUID algorithm or business-input markers are used.
    """

    def __init__(self, context: RoleExecutionContext, workflow: dict[str, Any], *,
                 event_wait_seconds: float = 5.0):
        self._positions = {
            (step["name"], index): task
            for step in workflow["steps"]
            for index, task in enumerate(step["subtasks"])
        }
        self._identities: dict[tuple[str, str], RoleTaskIdentity] = {}
        self._position_keys: dict[tuple[str, int], tuple[str, str]] = {}
        self._ready: dict[tuple[str, str], asyncio.Event] = {}
        self._sdk_execution_id: str | None = None
        self._error: BusinessFailure | None = None
        self._event_wait_seconds = event_wait_seconds
        self.context = replace(context, _task_identities=MappingProxyType(self._identities))

    def observe(self, event: dict) -> None:
        """Register task coordinates without changing the event sent to clients."""
        if event.get("type") != EventType.TASK_REQUEST or self._error is not None:
            return
        data = event.get("data", {})
        if not isinstance(data, dict):
            self._reject("Invalid SDK task event")
            return
        execution_id, task_id = data.get("execution_id"), data.get("task_id")
        step, index = data.get("step"), data.get("subtask_index")
        valid = (isinstance(execution_id, str) and bool(execution_id.strip())
                 and isinstance(task_id, str) and bool(task_id.strip())
                 and isinstance(step, str) and type(index) is int)
        position = (step, index) if valid else None
        source = self._positions.get(position)
        key = (execution_id, task_id)
        if (source is None or data.get("agent") != source["agent"]
                or self._sdk_execution_id not in (None, execution_id)
                or (key in self._identities and (
                    self._identities[key].step_name, self._identities[key].subtask_index) != position)
                or self._position_keys.get(position, key) != key):
            self._reject("Invalid SDK task coordinates")
            return
        self._sdk_execution_id = execution_id
        self._identities[key] = RoleTaskIdentity(
            task_id=source["task_id"], step_name=step, subtask_index=index,
            sdk_execution_id=execution_id, sdk_task_id=task_id,
        )
        self._position_keys[position] = key
        if key in self._ready:
            self._ready[key].set()
        logger.info(
            "[RoleHost] task mapping execution_id={} task_id={} sdk_execution_id={} sdk_task_id={} subtask_index={}",
            self.context.execution_id, source["task_id"], execution_id, task_id, index,
        )

    def _reject(self, message: str) -> BusinessFailure:
        # BusinessFailure preserves structured diagnostics through SDK results.
        self._error = BusinessFailure("INSTANCE_SNAPSHOT_MISMATCH", message, details={
            "reason": "SDK_TASK_MAPPING", "execution_id": self.context.execution_id,
        })
        for ready in self._ready.values():
            ready.set()
        logger.warning("[RoleHost] task mapping rejected execution_id={} reason=SDK_TASK_MAPPING",
                       self.context.execution_id)
        return self._error

    async def wait_for_task(self, request: TaskRequest) -> None:
        key = (request.execution_id, request.task_id)
        if self._error is None and key not in self._identities:
            ready = self._ready.setdefault(key, asyncio.Event())
            try:
                # Local queue delivery only; this never waits for an agent/LLM.
                await asyncio.wait_for(ready.wait(), timeout=self._event_wait_seconds)
            except TimeoutError as exc:
                raise self._reject("Missing SDK task event") from exc
            finally:
                self._ready.pop(key, None)
        if self._error is not None:
            raise self._error
        try:
            identity = self.context.task_identity(request)
        except LookupError as exc:
            raise self._reject("SDK callback has no matching task") from exc
        source = self._positions[(identity.step_name, identity.subtask_index)]
        if (request.agent_name, request.skill) != (source["agent"], source["skill"]):
            raise self._reject("SDK callback differs from mapped task")

    def wrap(self, policy: ControlPoint) -> ControlPoint:
        return _MappedControlPoint(self, policy)


class _MappedControlPoint(ControlPoint):
    """Gate task callbacks; preserve the SDK's native requests and policy results."""

    def __init__(self, bridge: RoleExecutionBridge, policy: ControlPoint):
        self._bridge, self._policy = bridge, policy

    async def on_task(self, request: TaskRequest) -> MessageContent:
        await self._bridge.wait_for_task(request)
        return await self._policy.on_task(request)

    async def on_self_task(self, request: TaskRequest) -> TaskResult:
        await self._bridge.wait_for_task(request)
        return await self._policy.on_self_task(request)

    async def on_route(self, request: RouteRequest) -> RouteDecision:
        return await self._policy.on_route(request)

    async def on_negotiation(self, request: NegotiationRequest) -> NegotiationReply:
        return await self._policy.on_negotiation(request)
