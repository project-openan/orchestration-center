# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Original task identities survive SDK-generated IDs and concurrent callbacks."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from a2a.types import AgentCard, TaskState
from google.protobuf.json_format import ParseDict
from workflow_engine import (
    BusinessFailure, BusinessInput, ControlPoint, MessageContent, RouteDecision,
    StubWorkflowEngineClient, TaskRequest, TaskResult,
)

from host_agent.config import RoleExecutionContext
from host_agent.role_execution import RoleExecutionBridge
from orchestrate.core.model.psop import JumpCondition, Step
from orchestrate.core.model.role_execution_snapshot import freeze_role_execution
from test_host_role_snapshot import Queue, context, envelope, executor
from test_role_pilot_delivery import prepared


def repeated_task_snapshot(first_step_type="AllSuccess"):
    template, result, cards = prepared()
    # The first two tasks are deliberately identical except for original ID.
    for task_id in ("t2", "t3"):
        source = template.steps[0].subtasks[0].model_copy(update={"task_id": task_id})
        bound = result.execution_psop.steps[0].subtasks[0].model_copy(update={"task_id": task_id})
        result.bindings.append({**deepcopy(result.bindings[0]), "task_id": task_id})
        if task_id == "t2":
            template.steps[0].subtasks.append(source)
            result.execution_psop.steps[0].subtasks.append(bound)
        else:
            template.steps.append(Step(name="again", subtasks=[source]))
            result.execution_psop.steps.append(Step(name="again", subtasks=[bound]))
    for workflow in (template, result.execution_psop):
        workflow.steps[0] = Step.model_validate({**workflow.steps[0].model_dump(), "type": first_step_type})
        workflow.steps[0].next = [JumpCondition(step="again", condition="continue")]
        workflow.steps.append(Step.model_validate(dict(name="legacy", subtasks=[dict(
            task_id="old", agent="Legacy", skill="existing", description="Existing task")])))
        workflow.steps.append(Step.model_validate(dict(name="local", type="SelfLoop", subtasks=[dict(
            task_id="self", agent="Host", skill="merge", description="Local merge")])))
    return freeze_role_execution(template, result, cards, "center-execution", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")


@pytest.mark.asyncio
@pytest.mark.parametrize("step_type", ["AllSuccess", "AnySuccess"])
async def test_host_policy_resolves_original_ids_with_real_sdk_concurrency(step_type):
    snapshot = repeated_task_snapshot(step_type)
    _, metadata = envelope(snapshot)
    seen, contexts, routes = {}, [], []
    both_started = asyncio.Event()

    class Policy(ControlPoint):
        def __init__(self, control_context):
            self.execution = control_context.role_execution
            contexts.append(self.execution)

        async def on_task(self, request):
            identity = self.execution.task_identity(request)
            binding = self.execution.binding_for(request)
            seen[identity.task_id] = (identity, binding, request)
            if identity.task_id in {"t1", "t2"}:
                if {"t1", "t2"} <= seen.keys():
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), 2)
            return MessageContent.text("content unchanged")

        async def on_self_task(self, request):
            identity = self.execution.task_identity(request)
            seen[identity.task_id] = (identity, self.execution.binding_for(request), request)
            return TaskResult.succeeded(("merged",))

        async def on_route(self, request):
            routes.append(request)
            return RouteDecision.allow("continue")

    host = executor([ParseDict(snapshot.cards[0].card, AgentCard())])
    host._control_point_factory = Policy
    host._engine_client_factory = SimpleNamespace(create=lambda _: StubWorkflowEngineClient())
    queue = Queue()
    await host.execute(context(metadata), queue)
    assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
    assert set(seen) == {"t1", "t2", "t3", "old", "self"}
    assert len(contexts) == len(routes) == 1
    assert contexts[0].execution_id == snapshot.execution_id
    sdk_execution_ids = {request.execution_id for _, _, request in seen.values()}
    assert len(sdk_execution_ids) == 1
    assert snapshot.execution_id not in sdk_execution_ids
    assert routes[0].execution_id in sdk_execution_ids
    assert len({identity.sdk_task_id for identity, _, _ in seen.values()}) == len(seen)
    for task_id, (identity, binding, request) in seen.items():
        assert (identity.sdk_execution_id, identity.sdk_task_id) == (request.execution_id, request.task_id)
        assert identity.step_name == request.step_name
        if task_id.startswith("t"):
            assert binding.task_id == task_id
        else:
            assert binding is None
        with pytest.raises(LookupError):
            contexts[0].binding_for(replace(request, execution_id="another-execution"))
    assert seen["t1"][0].subtask_index == 0
    assert seen["t2"][0].subtask_index == 1
    assert seen["t3"][0].step_name == "again"
    # Mapping never changes SDK IDs, task instructions or business inputs.
    for task_id in ("t1", "t2", "t3"):
        assert seen[task_id][2].instruction == seen[task_id][2].input.text == "Explore"
    sdk_events = [json.loads(event.metadata["__sdk_event__"]) for event in queue.events
                  if hasattr(event, "metadata") and "__sdk_event__" in event.metadata]
    assert len([event for event in sdk_events if event["type"] == "task_request"]) == 5


def bridge_case():
    snapshot = repeated_task_snapshot()
    bridge = RoleExecutionBridge(RoleExecutionContext(
        execution_id=snapshot.execution_id, caller_id=snapshot.context.caller_id,
        scope=snapshot.context.scope, bindings=tuple(snapshot.bindings),
    ), snapshot.execution_psop.model_dump(mode="json"), event_wait_seconds=0.05)
    request = TaskRequest(execution_id="sdk-execution", task_id="sdk-task",
        input=BusinessInput.from_data({"unchanged": [1, 2]}), agent_name=snapshot.bindings[0].agent,
        skill=snapshot.bindings[0].execution_skill, instruction="Explore", step_name="explore")
    event = {"type": "task_request", "data": dict(execution_id=request.execution_id,
        task_id=request.task_id, step=request.step_name, subtask_index=0, agent=request.agent_name)}
    policy = SimpleNamespace(on_task=AsyncMock(return_value=MessageContent.text("unchanged")),
        on_self_task=AsyncMock(), on_route=AsyncMock(), on_negotiation=AsyncMock())
    return bridge, request, event, policy


@pytest.mark.asyncio
async def test_callback_waits_for_event_and_preserves_content_and_negotiation():
    bridge, request, event, policy = bridge_case()
    wrapped = bridge.wrap(policy)
    callback = asyncio.create_task(wrapped.on_task(request))
    await asyncio.sleep(0)  # Force callback-before-event scheduling.
    assert not callback.done()
    policy.on_task.assert_not_awaited()
    original = deepcopy(event)
    bridge.observe(event)
    assert event == original
    assert await callback is policy.on_task.return_value
    assert policy.on_task.await_args.args[0] is request
    identity = bridge.context.task_identity(request)
    assert identity.task_id == "t1"
    with pytest.raises(TypeError):
        bridge.context._task_identities[(request.execution_id, request.task_id)] = identity
    binding = bridge.context.binding_for(request)
    binding.candidates.clear()
    assert bridge.context.binding_for(request).candidates
    negotiation = SimpleNamespace(task=request)
    assert await wrapped.on_negotiation(negotiation) is policy.on_negotiation.return_value
    policy.on_negotiation.assert_awaited_once_with(negotiation)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["step", "negative_index", "index_type", "agent", "execution_id", "task_id", "reused_task_id", "data"])
async def test_bad_or_conflicting_sdk_coordinates_never_reach_policy(change):
    bridge, request, event, policy = bridge_case()
    bridge.observe(event)
    changed = deepcopy(event)
    if change == "step":
        changed["data"]["step"] = "unknown"
    elif change == "negative_index":
        changed["data"]["subtask_index"] = -1
    elif change == "index_type":
        changed["data"]["subtask_index"] = True
    elif change == "agent":
        changed["data"]["agent"] = "wrong-agent"
    elif change == "execution_id":
        changed["data"]["execution_id"] = "other-sdk-execution"
    elif change == "task_id":
        # The same source position cannot acquire a second SDK task ID.
        changed["data"]["task_id"] = "second-sdk-task"
    elif change == "reused_task_id":
        changed["data"]["subtask_index"] = 1
    else:
        changed["data"] = None
    bridge.observe(changed)
    with pytest.raises(BusinessFailure) as failure:
        await bridge.wrap(policy).on_task(request)
    assert failure.value.code == "INSTANCE_SNAPSHOT_MISMATCH"
    assert failure.value.details["reason"] == "SDK_TASK_MAPPING"
    policy.on_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("agent_name", "wrong"), ("skill", "wrong"), ("step_name", "again")])
async def test_callback_must_match_registered_source_task(field, value):
    bridge, request, event, policy = bridge_case()
    bridge.observe(event)
    with pytest.raises(BusinessFailure):
        await bridge.wrap(policy).on_task(replace(request, **{field: value}))
    policy.on_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_event_fails_closed_and_cancellation_stops_waiting():
    bridge, request, _, policy = bridge_case()
    with pytest.raises(BusinessFailure, match="Missing SDK task event"):
        await bridge.wrap(policy).on_task(request)
    policy.on_task.assert_not_awaited()
    bridge, request, _, policy = bridge_case()
    callback = asyncio.create_task(bridge.wrap(policy).on_task(request))
    await asyncio.sleep(0)
    callback.cancel()
    with pytest.raises(asyncio.CancelledError):
        await callback
    assert not bridge._ready
    policy.on_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapping_is_isolated_between_concurrent_executions():
    cases = [bridge_case(), bridge_case()]
    for index, (bridge, request, event, _) in enumerate(cases):
        event["data"]["execution_id"] = f"sdk-execution-{index}"
        bridge.observe(event)
    async def resolve(index):
        bridge, request, _, policy = cases[index]
        own = replace(request, execution_id=f"sdk-execution-{index}")
        await bridge.wrap(policy).on_task(own)
        with pytest.raises(LookupError):
            cases[1 - index][0].context.binding_for(own)
        return bridge.context.binding_for(own).task_id
    assert await asyncio.gather(resolve(0), resolve(1)) == ["t1", "t1"]


@pytest.mark.asyncio
async def test_mapping_failure_survives_sdk_result_and_prevents_dispatch(monkeypatch):
    snapshot = repeated_task_snapshot()
    _, metadata = envelope(snapshot)
    original = RoleExecutionBridge.observe
    def corrupt_coordinates(bridge, event):
        if event["type"] == "task_request":
            event = deepcopy(event)
            event["data"]["subtask_index"] = 99
        original(bridge, event)
    monkeypatch.setattr(RoleExecutionBridge, "observe", corrupt_coordinates)
    client = StubWorkflowEngineClient()
    client.close = AsyncMock()
    host = executor([ParseDict(snapshot.cards[0].card, AgentCard())])
    host._engine_client_factory = SimpleNamespace(create=lambda _: client)
    queue = Queue()
    await host.execute(context(metadata), queue)
    assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
    assert not client.sent
    client.close.assert_awaited_once()
    events = [json.loads(event.metadata["__sdk_event__"]) for event in queue.events
              if hasattr(event, "metadata") and "__sdk_event__" in event.metadata]
    responses = [event["data"] for event in events if event["type"] == "task_response"]
    assert responses
    assert all(data["error_code"] == "INSTANCE_SNAPSHOT_MISMATCH" for data in responses)
    assert all(data["error_details"]["reason"] == "SDK_TASK_MAPPING" for data in responses)
