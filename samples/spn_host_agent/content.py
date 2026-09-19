# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""A2A-T 1.1 business-content helpers for the SPN Workbench agent."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from a2a.types import Part
from a2a_t.client import A2ATClient
from a2a_t.core import (
    NEGOTIATION_CONTEXT_METADATA_KEY,
    TEMPLATE_URI_METADATA_KEY,
    NegotiationContext,
)
from a2a_t.core.metadata import (
    NEGOTIATION_T_EXTENSION_URI,
    TASK_T_EXTENSION_URI,
)
from a2a_t.core.standard_templates import (
    AUTHORIZATION_POLICY_MANAGEMENT_URI,
    INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI,
    INFORMATION_NEGOTIATION_PROPOSE_URI,
    NEGOTIATION_ABORT_URI,
    PRIVATE_LINE_COMPLAINT_URI,
    SERVICE_RECOVERY_URI,
)
from a2a_t.negotiation.content import (
    InformationEndingContent,
    NegotiationAbortContent,
    NegotiationAbortData,
    NegotiationConclusion,
    NegotiationEndingData,
    NegotiationItem,
)
from a2a_t.server import A2ATServer
from workflow_engine import A2atMessages, MessageContent, ReceivedMessage, TaskRequest

TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "任务对象": {
            "type": "string",
            "description": (
                "必选。使用专线业务名称、专线业务标识或专线业务接入端口名称之一标识"
                "被投诉对象；接入端口使用“接入端口名称：端口(cvlan=接入VLAN)”格式。"
            ),
        },
        "任务上下文": {
            "type": "string",
            "description": "投诉分类和OSS侧事件流水号必填；问题发生时间及投诉详情可选。",
        },
    },
    "required": ["任务上下文", "任务对象"],
}

AUTHORIZATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "授权策略的操作类型": {
            "type": "string",
            "description": "授权策略操作类型，本示例使用新增授权策略。",
        },
        "动网操作的授权策略列表": {
            "type": "string",
            "description": "按编号列出的授权策略，包含业务场景、处置类型、操作名称和有效期。",
        },
    },
    "required": ["授权策略的操作类型", "动网操作的授权策略列表"],
}

NOTIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "订阅条件": {
            "type": "string",
            "description": "订阅业务抢通结果的子网范围。",
        },
        "上报通知数据格式": {
            "type": "string",
            "description": "业务抢通结果通知必须携带的字段和条件必填字段。",
        },
    },
    "required": ["订阅条件", "上报通知数据格式"],
}

NEGOTIATION_ITEMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "逐字提取所需信息项中编号后、冒号前的字段名称。",
        },
        "relationship": {
            "type": "string",
            "nullable": True,
            "description": "请求字段必须一起提供时为AND，明确为替代项时为OR，未说明可为空。",
        },
    },
    "required": ["items"],
}

RECOVERY_RESULT_REQUIRED_FIELDS = frozenset({
    "业务抢通方案执行状态",
    "投诉诊断任务流水号",
    "OSS侧事件流水号",
    "接入端口名称",
    "是否已授权OMC自动抢通",
    "业务抢通方案名称",
    "业务抢通方案详情",
    "业务抢通方案执行结束时间",
    "业务抢通方案执行结果",
    "业务抢通方案执行失败原因",
})


def create_a2at_client() -> A2ATClient:
    return A2ATClient(env_path=Path(__file__).resolve().parents[2] / ".env")


def create_a2at_server() -> A2ATServer:
    return A2ATServer(env_path=Path(__file__).resolve().parents[2] / ".env")


def complaint_data(request: TaskRequest) -> dict[str, object]:
    if request.input.data is not None:
        if not isinstance(request.input.data, Mapping):
            raise ValueError("SPN complaint input must be an object")
        return dict(request.input.data)
    common_context = (
        '投诉分类："专线质差"；问题发生时间："2026-05-11T08:21:46Z"；'
        'OSS侧事件流水号："event-id-20260511-09013"；'
        '投诉详情："跨城访问响应延迟由12ms升至320ms。"'
    )
    if request.step_name == "diagnosis_city1":
        return {
            "任务对象": "接入端口名称：P781-珠江新城-PTN7900-23-TPA1EG24-17(cvlan=100)",
            "任务上下文": common_context,
        }
    if request.step_name == "diagnosis_city2":
        return {
            "任务对象": "接入端口名称：P882-珠江新城-PTN7900-23-TPA1EG24-11(cvlan=200)",
            "任务上下文": common_context,
        }
    raise ValueError(f"No SPN complaint data configured for step {request.step_name}")


def task_content(client: A2ATClient, request: TaskRequest) -> MessageContent:
    generated = client.generate_task_prompt_from_data_with_schema(
        complaint_data(request), TASK_SCHEMA, PRIVATE_LINE_COMPLAINT_URI
    )
    if request.step_name == "diagnosis_city1":
        prompt = generated.prompt_text or ""
        start = prompt.find("## 任务对象")
        end = prompt.find("## 任务上下文", start)
        if start < 0 or end < 0:
            raise ValueError("Generated Task-T content has no task-object section")
        generated = type(generated)(
            generated.template_uri,
            prompt[:start] + "## 任务对象(Task Object)\n接入端口名称：\n\n" + prompt[end:],
            generated.extension_uri,
            generated.negotiation_context,
        )
    return A2atMessages.from_generated(generated, (Part(text=request.instruction),))


def authorization_content(client: A2ATClient) -> MessageContent:
    generated = client.generate_auth_prompt_from_data_with_schema(
        {
            "授权策略的操作类型": "新增授权策略",
            "动网操作的授权策略列表": (
                "1. 业务场景是业务投诉诊断，处置类型是业务抢通，"
                "操作名称是光模块更换，有效期是2026-06-01~2030-06-18"
            ),
        },
        AUTHORIZATION_SCHEMA,
        AUTHORIZATION_POLICY_MANAGEMENT_URI,
    )
    return A2atMessages.from_generated(generated, (Part(text="下发授权放行策略"),))


def notification_content(client: A2ATClient) -> MessageContent:
    generated = client.generate_notification_prompt_from_data_with_schema(
        {
            "订阅条件": "子网名称：SPN承载子网",
            "上报通知数据格式": (
                "业务抢通事件数据包含：执行状态、投诉诊断任务流水号、OSS侧事件流水号、"
                "接入端口名称、自动抢通授权状态、方案名称、方案详情、执行结束时间、"
                "执行结果，以及执行失败时必填的失败原因。"
            ),
        },
        NOTIFICATION_SCHEMA,
        SERVICE_RECOVERY_URI,
    )
    return A2atMessages.from_generated(generated, (Part(text="订阅业务抢通结果通知"),))


def metadata_for(received: ReceivedMessage, extension_uri: str) -> Mapping[str, Any]:
    layers: list[Mapping[str, Any]] = []
    if received.message is not None:
        layers.append(received.message.metadata)
    layers.append(received.task_metadata)
    layers.extend(artifact.metadata for artifact in received.artifacts)
    matches = [layer for layer in layers if extension_uri in layer]
    if not matches:
        raise ValueError(f"No {extension_uri} metadata layer was received")
    protocol_keys = (
        extension_uri,
        TEMPLATE_URI_METADATA_KEY,
        NEGOTIATION_CONTEXT_METADATA_KEY,
    )
    canonical: dict[str, Any] = {}
    for layer in matches:
        for key in protocol_keys:
            if key not in layer:
                continue
            if key in canonical and canonical[key] != layer[key]:
                raise ValueError(f"Conflicting {extension_uri} metadata layers were received")
            canonical[key] = layer[key]
    return canonical


def negotiation_prompt(received: ReceivedMessage) -> tuple[str, str]:
    metadata = metadata_for(received, NEGOTIATION_T_EXTENSION_URI)
    prompt = metadata.get(NEGOTIATION_T_EXTENSION_URI)
    template_uri = metadata.get(TEMPLATE_URI_METADATA_KEY)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Negotiation-T prompt is missing")
    if not isinstance(template_uri, str) or not template_uri.strip():
        raise ValueError("Negotiation-T templateUri is missing")
    return prompt, template_uri


def negotiation_accept_content(
    client: A2ATClient,
    context: NegotiationContext,
    answers: list[NegotiationItem],
    message: str,
) -> MessageContent:
    generated = client.generate_negotiation_accept_prompt_from_data(
        NegotiationEndingData(
            context,
            InformationEndingContent(NegotiationConclusion.ACCEPT, answers),
        ),
        INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI,
    )
    return A2atMessages.from_generated(generated, (Part(text=message),))


def negotiation_reject_content(
    client: A2ATClient,
    context: NegotiationContext,
    reason: str,
) -> MessageContent:
    generated = client.generate_negotiation_reject_prompt_from_data(
        NegotiationEndingData(
            context,
            InformationEndingContent(
                NegotiationConclusion.REJECT,
                [NegotiationItem("拒绝原因", reason)],
            ),
        ),
        INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI,
    )
    return A2atMessages.from_generated(generated, (Part(text=reason),))


def negotiation_abort_content(
    client: A2ATClient,
    context: NegotiationContext,
    reason: str,
) -> MessageContent:
    generated = client.generate_negotiation_abort_prompt_from_data(
        NegotiationAbortData(context, NegotiationAbortContent(reason)),
        NEGOTIATION_ABORT_URI,
    )
    return A2atMessages.from_generated(generated, (Part(text=reason),))


__all__ = [
    "AUTHORIZATION_SCHEMA",
    "INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI",
    "INFORMATION_NEGOTIATION_PROPOSE_URI",
    "NEGOTIATION_ABORT_URI",
    "NEGOTIATION_ITEMS_SCHEMA",
    "NOTIFICATION_SCHEMA",
    "PRIVATE_LINE_COMPLAINT_URI",
    "TASK_SCHEMA",
    "TASK_T_EXTENSION_URI",
    "authorization_content",
    "complaint_data",
    "create_a2at_client",
    "create_a2at_server",
    "metadata_for",
    "negotiation_abort_content",
    "negotiation_accept_content",
    "negotiation_prompt",
    "negotiation_reject_content",
    "notification_content",
    "RECOVERY_RESULT_REQUIRED_FIELDS",
    "task_content",
]
