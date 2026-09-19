# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import threading
import uuid
from types import SimpleNamespace

import pytest
from a2a.types import Part, TaskState
from a2a_t.core import (
    MetadataContent,
    NEGOTIATION_CONTEXT_METADATA_KEY,
    TEMPLATE_URI_METADATA_KEY,
    NegotiationContext,
    NegotiationPerformative,
)
from a2a_t.core.metadata import (
    NEGOTIATION_T_EXTENSION_URI,
    NOTIFICATION_T_EXTENSION_URI,
)
from a2a_t.core.standard_templates import SERVICE_RECOVERY_URI
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Value
from samples.agents.host_execution import HostExecutionTracker
from samples.agents.live_streaming_agent import (
    LiveStreamingAgentExecutor,
    LiveStreamingControlPoint,
)
from samples.agents.negotiation_base_agent import NegotiationBaseAgentExecutor
from samples.agents.spn_domain_agent import SpnDomainAgentExecutor
from samples.spn_host_agent.lifecycle import SpnExtensionLifecycle
from samples.spn_host_agent.content import (
    INFORMATION_NEGOTIATION_PROPOSE_URI,
    RECOVERY_RESULT_REQUIRED_FIELDS,
)
from samples.spn_host_agent import SpnControlPoint
from host_agent.runtime import HostAgentExecutor
from workflow_engine import (
    A2atMessages,
    BusinessInput,
    MessageContent,
    NegotiationRequest,
    ReceivedArtifact,
    ReceivedMessage,
    RouteRequest,
    SendMessageResult,
    TaskExecutionResult,
    TaskRequest,
    WorkflowInput,
)
from workflow_engine import TaskStatus as EngineTaskStatus


class _NegotiationClient:
    def __init__(self, requested_fields):
        self._requested_fields = requested_fields

    def validate_propose_prompt_and_data_filling(self, *args, **kwargs):
        del args, kwargs
        return SimpleNamespace(data={"items": self._requested_fields, "relationship": "AND"})

    def generate_negotiation_accept_prompt_from_data(self, data, template_uri):
        answers = "; ".join(f"{item.name}={item.value}" for item in data.content.items)
        return MetadataContent(
            template_uri,
            f"accept: {answers}",
            NEGOTIATION_T_EXTENSION_URI,
            data.context.with_performative(NegotiationPerformative.ACCEPT),
        )

    def generate_negotiation_reject_prompt_from_data(self, data, template_uri):
        return MetadataContent(
            template_uri,
            "reject",
            NEGOTIATION_T_EXTENSION_URI,
            data.context.with_performative(NegotiationPerformative.REJECT),
        )


class _EventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class _RouteLlm:
    def __init__(self, decisions):
        self._decisions = iter(decisions)
        self.prompts = []

    def ask_llm(self, prompt):
        self.prompts.append(prompt)
        return None, next(self._decisions)


def _task_request(step_name: str, agent_name: str) -> TaskRequest:
    return TaskRequest(
        execution_id="execution-1",
        task_id=f"task-{step_name}",
        input=BusinessInput.from_text("执行任务"),
        agent_name=agent_name,
        skill="diagnosis",
        instruction="执行任务",
        step_name=step_name,
    )


def _proposal_request(task: TaskRequest, requested_field: str) -> NegotiationRequest:
    context = NegotiationContext(
        str(uuid.uuid4()),
        1,
        3,
        NegotiationPerformative.PROPOSE,
    )
    metadata = {
        NEGOTIATION_T_EXTENSION_URI: f"请补充{requested_field}",
        TEMPLATE_URI_METADATA_KEY: INFORMATION_NEGOTIATION_PROPOSE_URI,
        NEGOTIATION_CONTEXT_METADATA_KEY: {
            "id": context.id,
            "round": context.round,
            "maxRounds": context.max_rounds,
            "performative": context.performative.value,
        },
    }
    return NegotiationRequest(
        task=task,
        original_submission=MessageContent.text(task.instruction),
        received=ReceivedMessage(task_metadata=metadata),
        previous_exchanges=(),
        remaining_wait_seconds=30,
    )


def _recovery_result() -> dict:
    return {
        "业务抢通方案执行状态": "已结束",
        "投诉诊断任务流水号": "task-1",
        "OSS侧事件流水号": "event-1",
        "接入端口名称": "port-1",
        "是否已授权OMC自动抢通": "是",
        "业务抢通方案名称": "plan-1",
        "业务抢通方案详情": "done",
        "业务抢通方案执行结束时间": "2026-09-10T00:00:00+00:00",
        "业务抢通方案执行结果": "成功",
        "业务抢通方案执行失败原因": "",
    }


@pytest.mark.asyncio
async def test_spn_host_negotiation_uses_current_city_task_data():
    control_point = SpnControlPoint.__new__(SpnControlPoint)
    control_point.a2at_client = _NegotiationClient(["任务对象"])
    request = _proposal_request(
        _task_request("diagnosis_city2", "SPN Domain Agent City2"),
        "任务对象",
    )

    reply = await control_point.on_negotiation(request)

    context = A2atMessages.context_from_metadata(reply.content.metadata)
    assert context.performative is NegotiationPerformative.ACCEPT
    assert "P882-珠江新城-PTN7900-23-TPA1EG24-11(cvlan=200)" in reply.content.metadata[
        NEGOTIATION_T_EXTENSION_URI
    ]
    assert "P781-" not in reply.content.metadata[NEGOTIATION_T_EXTENSION_URI]


@pytest.mark.asyncio
async def test_spn_host_sends_reject_when_requested_field_is_unavailable():
    control_point = SpnControlPoint.__new__(SpnControlPoint)
    control_point.a2at_client = _NegotiationClient(["不存在字段"])
    request = _proposal_request(
        _task_request("diagnosis_city1", "SPN Domain Agent City1"),
        "不存在字段",
    )

    reply = await control_point.on_negotiation(request)

    assert (
        A2atMessages.context_from_metadata(reply.content.metadata).performative
        is NegotiationPerformative.REJECT
    )


@pytest.mark.asyncio
async def test_live_streaming_resolves_ran_sla_negotiation():
    control_point = LiveStreamingControlPoint.__new__(LiveStreamingControlPoint)
    control_point.a2at_client = _NegotiationClient(["SLA授权方案"])
    request = _proposal_request(
        _task_request("ran_energy_saving", "Wireless Domain Agent"),
        "SLA授权方案",
    )

    reply = await control_point.on_negotiation(request)

    context = A2atMessages.context_from_metadata(reply.content.metadata)
    assert context.performative is NegotiationPerformative.ACCEPT
    assert "PRB利用率" in reply.content.metadata[NEGOTIATION_T_EXTENSION_URI]


@pytest.mark.asyncio
@pytest.mark.parametrize("control_point_type", [SpnControlPoint, LiveStreamingControlPoint])
async def test_route_callback_evaluates_each_conditional_edge_independently(
    control_point_type,
):
    control_point = control_point_type.__new__(control_point_type)
    control_point.llm_client = _RouteLlm(["true", "false"])
    current_results = (
        TaskExecutionResult(
            agent_name="agent-1",
            skill="diagnosis",
            task_id="task-1",
            task_description="diagnose",
            status=EngineTaskStatus.SUCCESS,
            outputs=("fault found",),
        ),
    )
    common = {
        "execution_id": "execution-1",
        "step_name": "diagnosis",
        "workflow_input": WorkflowInput(),
        "current_results": current_results,
    }

    first = await control_point.on_route(RouteRequest(
        next_step="repair",
        condition="fault found",
        **common,
    ))
    second = await control_point.on_route(RouteRequest(
        next_step="manual_review",
        condition="diagnosis inconclusive",
        **common,
    ))

    assert first.allowed is True
    assert second.allowed is False
    assert "Candidate next step: repair" in control_point.llm_client.prompts[0]
    assert "Candidate next step: manual_review" in control_point.llm_client.prompts[1]


def test_spn_task_returns_diagnosis_without_notification_payload(monkeypatch):
    executor = SpnDomainAgentExecutor.__new__(SpnDomainAgentExecutor)
    published = []
    monkeypatch.setattr(
        NegotiationBaseAgentExecutor,
        "_execute_task",
        lambda *args, **kwargs: "diagnosis-only",
    )
    monkeypatch.setattr(
        executor,
        "_self_trigger_recovery",
        lambda *args: published.append(args),
    )

    result = executor._execute_task("task-input", "task-1", "context-1")

    assert result == "diagnosis-only"
    assert published == [("diagnosis-only", "task-input", "task-1")]


def test_spn_recovery_notification_contains_complete_business_result(monkeypatch):
    executor = SpnDomainAgentExecutor.__new__(SpnDomainAgentExecutor)
    executor._authorization_policy = "业务抢通 光模块 授权"
    published = []
    monkeypatch.setattr(executor, "_llm_recovery", lambda diagnosis: "端口恢复Up")
    monkeypatch.setattr(executor, "push_notification_result", published.append)

    executor._self_trigger_recovery(
        "diagnosis",
        "接入端口名称：P781-port；OSS侧事件流水号：event-1；",
        "task-1",
    )

    assert len(published) == 1
    assert set(published[0]) == RECOVERY_RESULT_REQUIRED_FIELDS
    assert published[0]["业务抢通方案执行结果"] == "成功"
    assert published[0]["投诉诊断任务流水号"] == "task-1"


def test_spn_agent_rejects_another_city_task_object():
    executor = SpnDomainAgentExecutor.__new__(SpnDomainAgentExecutor)
    executor._expected_task_object = "city1-port"

    assert executor._semantic_invalid_fields({"任务对象": "city2-port"}) == {"任务对象"}
    assert executor._semantic_invalid_fields({"任务对象": "city1-port"}) == set()


@pytest.mark.asyncio
async def test_notification_subscription_emits_ack_then_completed_result():
    executor = NegotiationBaseAgentExecutor.__new__(NegotiationBaseAgentExecutor)
    executor.a2at_server = SimpleNamespace(
        validate_notification_prompt_and_data_filling=lambda *args: None
    )
    executor._notification_subscribers = {}
    executor._notification_backlog = [_recovery_result()]
    executor._notification_lock = threading.Lock()
    executor._shutdown = False
    context = SimpleNamespace(task_id="notification-1", context_id="context-1")
    event_queue = _EventQueue()

    await executor._handle_notification_subscription(
        context,
        event_queue,
        {
            NOTIFICATION_T_EXTENSION_URI: "subscription",
            TEMPLATE_URI_METADATA_KEY: SERVICE_RECOVERY_URI,
        },
    )

    assert [event.status.state for event in event_queue.events] == [
        TaskState.TASK_STATE_WORKING,
        TaskState.TASK_STATE_COMPLETED,
    ]
    assert event_queue.events[0].artifacts[0].name == "notification-subscription"
    assert event_queue.events[1].artifacts[0].name == "recovery-result"


@pytest.mark.asyncio
async def test_notification_listener_distinguishes_ack_and_completed_result():
    lifecycle = SpnExtensionLifecycle.__new__(SpnExtensionLifecycle)
    lifecycle._completed_notifications = set()
    subscription = SimpleNamespace(closed=False)
    subscription.close = lambda: setattr(subscription, "closed", True)
    acknowledgement = ReceivedMessage(
        artifacts=(ReceivedArtifact(name="notification-subscription"),)
    )

    lifecycle._on_notification(subscription, acknowledgement, "agent-1")

    assert not subscription.closed
    value = ParseDict(_recovery_result(), Value())
    result = ReceivedMessage(
        artifacts=(
            ReceivedArtifact(
                name="recovery-result",
                parts=(Part(data=value),),
            ),
        )
    )
    lifecycle._on_notification(subscription, result, "agent-1")
    await asyncio.sleep(0)
    assert "agent-1" in lifecycle._completed_notifications
    assert subscription.closed


@pytest.mark.asyncio
async def test_failed_authorization_is_retried_without_blocking_workflow(monkeypatch):
    lifecycle = SpnExtensionLifecycle.__new__(SpnExtensionLifecycle)
    lifecycle._authorization_targets = ("agent-1",)
    lifecycle._authorized = set()
    lifecycle._stop = asyncio.Event()
    lifecycle._authorization_sender = SimpleNamespace(
        send_authorization=lambda *args: asyncio.sleep(
            0,
            result=SendMessageResult(
                task_state="TASK_STATE_FAILED",
                failure_code="a2a.task_failed",
                failure_message="policy rejected",
            ),
        )
    )
    monkeypatch.setattr(
    "samples.spn_host_agent.lifecycle.create_a2at_client",
        lambda: object(),
    )
    monkeypatch.setattr(
    "samples.spn_host_agent.lifecycle.authorization_content",
        lambda client: MessageContent.text("authorization"),
    )

    await lifecycle._ensure_authorizations()

    assert lifecycle._authorized == set()


@pytest.mark.asyncio
async def test_failed_notification_ack_closes_and_removes_subscription(monkeypatch):
    loop = asyncio.get_running_loop()
    acknowledgement = loop.create_future()
    acknowledgement.set_result(SendMessageResult(
        task_state="TASK_STATE_FAILED",
        failure_code="a2a.task_failed",
        failure_message="subscription rejected",
    ))
    subscription = SimpleNamespace(
        acknowledgement=acknowledgement,
        is_active=True,
        closed=False,
    )
    subscription.close = lambda: setattr(subscription, "closed", True)
    lifecycle = SpnExtensionLifecycle.__new__(SpnExtensionLifecycle)
    lifecycle._notification_targets = ("agent-1",)
    lifecycle._completed_notifications = set()
    lifecycle._subscriptions = {}
    lifecycle._stop = asyncio.Event()
    lifecycle._notification_sender = SimpleNamespace(
        open_notification=lambda *args: subscription,
    )
    monkeypatch.setattr(
    "samples.spn_host_agent.lifecycle.create_a2at_client",
        lambda: object(),
    )
    monkeypatch.setattr(
    "samples.spn_host_agent.lifecycle.notification_content",
        lambda client: MessageContent.text("notification"),
    )

    await lifecycle._ensure_subscriptions()

    assert "agent-1" not in lifecycle._subscriptions
    assert subscription.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "executor_type",
    [NegotiationBaseAgentExecutor, HostAgentExecutor, LiveStreamingAgentExecutor],
)
async def test_cancel_returns_a2a_canceled_task(executor_type):
    executor = executor_type.__new__(executor_type)
    if executor_type is NegotiationBaseAgentExecutor:
        executor._pending = {}
        executor._notification_subscribers = {}
        executor._notification_lock = threading.Lock()
    else:
        executor._execution_tracker = HostExecutionTracker()
    context = SimpleNamespace(task_id="task-1", context_id="context-1")
    event_queue = _EventQueue()

    await executor.cancel(context, event_queue)

    assert event_queue.events[-1].status.state is TaskState.TASK_STATE_CANCELED


def test_host_executors_do_not_store_request_language(monkeypatch):
    monkeypatch.setattr("host_agent.runtime.get_conf", lambda: {})
    monkeypatch.setattr("samples.agents.live_streaming_agent.get_conf", lambda: {})

    assert not hasattr(HostAgentExecutor(control_point_factory=SpnControlPoint), "lang")
    assert not hasattr(LiveStreamingAgentExecutor(), "lang")
