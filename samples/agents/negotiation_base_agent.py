# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""A2A server-side simulation using the A2A-T 1.1 content pipeline."""

from __future__ import annotations

import asyncio
import json
import queue as queue_module
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Artifact, Part, Task, TaskState, TaskStatus
from a2a_t.core import (
    TEMPLATE_URI_METADATA_KEY,
    ContentValidationError,
    NegotiationContext,
    NegotiationPerformative,
)
from a2a_t.core.metadata import (
    AUTHORIZATION_T_EXTENSION_URI,
    NEGOTIATION_T_EXTENSION_URI,
    NOTIFICATION_T_EXTENSION_URI,
    TASK_T_EXTENSION_URI,
)
from a2a_t.core.standard_templates import (
    AUTHORIZATION_POLICY_MANAGEMENT_URI,
    SERVICE_RECOVERY_URI,
)
from a2a_t.negotiation.content import (
    InformationProposeContent,
    NegotiationItem,
    NegotiationProposeData,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from loguru import logger
from workflow_engine import A2atMessages

from common.llm import get_llm_instance
from samples.spn_host_agent.content import (
    AUTHORIZATION_SCHEMA,
    INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI,
    INFORMATION_NEGOTIATION_PROPOSE_URI,
    NEGOTIATION_ABORT_URI,
    NOTIFICATION_SCHEMA,
    PRIVATE_LINE_COMPLAINT_URI,
    TASK_SCHEMA,
    create_a2at_server,
)


@dataclass(frozen=True)
class _PendingNegotiation:
    a2a_context_id: str
    context: NegotiationContext
    validated_data: dict[str, object]
    requested_fields: tuple[str, ...]


class NegotiationBaseAgentExecutor(AgentExecutor):
    """Simulated worker with current Task-T and Negotiation-T processing."""

    def __init__(
        self,
        agent_prompt_template: str,
        expected_task_object: str | None = None,
    ) -> None:
        self.llm = get_llm_instance()
        self.a2at_server = create_a2at_server()
        self.prompt_template = agent_prompt_template
        self._expected_task_object = expected_task_object
        self._authorization_policy: str | None = None
        self._notification_subscribers: dict[
            str, queue_module.Queue[dict[str, Any] | None]
        ] = {}
        self._notification_backlog: list[dict[str, Any]] = []
        self._notification_lock = threading.Lock()
        self._pending: dict[str, _PendingNegotiation] = {}
        self._shutdown = False
        logger.info(f"[{self.__class__.__name__}] Initialized with A2A-T 1.1 content APIs")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        metadata = self._message_metadata(context)
        logger.info(
            f"[{self.__class__.__name__}] execute: task_id={context.task_id}, "
            f"context_id={context.context_id}"
        )
        if NOTIFICATION_T_EXTENSION_URI in metadata:
            await self._handle_notification_subscription(context, event_queue, metadata)
            return
        if AUTHORIZATION_T_EXTENSION_URI in metadata:
            await self._handle_authorization(context, event_queue, metadata)
            return
        if NEGOTIATION_T_EXTENSION_URI in metadata and TASK_T_EXTENSION_URI not in metadata:
            try:
                task = await self._handle_negotiation_reply(context, metadata)
            except Exception as error:
                logger.exception(
                    f"[{self.__class__.__name__}] Negotiation-T reply failed: "
                    f"task_id={context.task_id}, error={error}"
                )
                task = self._failed_task(
                    context, f"Negotiation-T reply processing failed: {error}"
                )
        else:
            task = await self._handle_task(context, metadata)
        await event_queue.enqueue_event(task)

    @staticmethod
    def _message_metadata(context: RequestContext) -> dict[str, Any]:
        message = getattr(context, "message", None)
        metadata = getattr(message, "metadata", None) if message is not None else None
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return dict(metadata)
        try:
            return MessageToDict(metadata, preserving_proto_field_name=True)
        except Exception:
            return dict(metadata)

    async def _handle_task(self, context: RequestContext, metadata: dict[str, Any]) -> Task:
        prompt = metadata.get(TASK_T_EXTENSION_URI)
        template_uri = metadata.get(TEMPLATE_URI_METADATA_KEY)
        if not isinstance(prompt, str) or not prompt.strip():
            return await self._run_business(context, context.get_user_input())
        if template_uri != PRIVATE_LINE_COMPLAINT_URI:
            raise ValueError(f"Unsupported Task-T template: {template_uri}")
        try:
            filled = await asyncio.to_thread(
                self.a2at_server.validate_task_prompt_and_data_filling,
                prompt,
                TASK_SCHEMA,
                template_uri,
            )
            data = dict(filled.data)
        except ContentValidationError as error:
            data = dict(error.params)
            invalid_fields = {item.slot_name for item in error.errors}
            logger.info(
                f"[{self.__class__.__name__}] Task-T validation requested negotiation: "
                f"code={error.code_str}, slots={sorted(invalid_fields)}"
            )
        else:
            invalid_fields = set()
        invalid_fields.update(self._semantic_invalid_fields(data))
        missing = tuple(
            name for name in TASK_SCHEMA["required"]
            if name in invalid_fields
            or not isinstance(data.get(name), str)
            or not str(data.get(name)).strip()
        )
        if missing:
            return await self._request_negotiation(context, data, missing)
        return await self._run_business(context, self._format_business_input(data))

    def _semantic_invalid_fields(self, data: Mapping[str, object]) -> set[str]:
        """Return business fields that are present but target the wrong agent."""
        if self._expected_task_object is None:
            return set()
        task_object = data.get("任务对象")
        if not isinstance(task_object, str) or self._expected_task_object not in task_object:
            logger.warning(
                f"[{self.__class__.__name__}] Task object does not belong to this agent: "
                f"expected={self._expected_task_object}, actual={task_object}"
            )
            return {"任务对象"}
        return set()

    def _negotiation_item_description(self, name: str) -> str:
        if name == "任务对象":
            return "请提供本地市实际接入端口名称"
        return "请提供投诉分类及OSS侧事件流水号"

    async def _request_negotiation(
        self,
        context: RequestContext,
        validated_data: dict[str, object],
        missing: tuple[str, ...],
    ) -> Task:
        negotiation_context = NegotiationContext(
            str(uuid.uuid4()),
            1,
            NegotiationContext.DEFAULT_MAX_ROUNDS,
            NegotiationPerformative.PROPOSE,
        )
        items = [
            NegotiationItem(name, self._negotiation_item_description(name))
            for name in missing
        ]
        generated = await asyncio.to_thread(
            self.a2at_server.generate_negotiation_propose_prompt_from_data,
            NegotiationProposeData(
                negotiation_context,
                InformationProposeContent(items, "AND：所列字段均为本次诊断必需"),
            ),
            INFORMATION_NEGOTIATION_PROPOSE_URI,
        )
        task_id = context.task_id or ""
        self._pending[task_id] = _PendingNegotiation(
            context.context_id or "",
            negotiation_context,
            dict(validated_data),
            missing,
        )
        logger.info(
            f"[{self.__class__.__name__}] Negotiation-T PROPOSE: "
            f"task_id={task_id}, fields={list(missing)}"
        )
        generated_metadata = generated.build_metadata_content()
        return Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
            artifacts=[Artifact(
                artifact_id=str(uuid.uuid4()),
                parts=[Part(text="存在信息缺失，请补充信息")],
                metadata=generated_metadata,
            )],
            metadata=generated_metadata,
        )

    async def _handle_negotiation_reply(
        self, context: RequestContext, metadata: dict[str, Any]
    ) -> Task:
        received_context = A2atMessages.context_from_metadata(metadata)
        pending = self._pending.get(context.task_id or "")
        if pending is None:
            raise ValueError("No pending negotiation for this task")
        expected = pending.context
        if (
            pending.a2a_context_id != (context.context_id or "")
            or received_context.id != expected.id
            or received_context.round != expected.round
            or received_context.max_rounds != expected.max_rounds
        ):
            raise ValueError("Negotiation reply does not match the pending task/context")
        prompt = metadata.get(NEGOTIATION_T_EXTENSION_URI)
        template_uri = metadata.get(TEMPLATE_URI_METADATA_KEY)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Negotiation-T reply prompt is missing")
        self._pending.pop(context.task_id or "", None)
        if received_context.performative == NegotiationPerformative.ACCEPT:
            if template_uri != INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI:
                raise ValueError(f"Unsupported Negotiation-T Accept template: {template_uri}")
            properties = {
                name: {"type": "string", "minLength": 1, "description": name}
                for name in pending.requested_fields
            }
            filled = await asyncio.to_thread(
                self.a2at_server.validate_accept_prompt_and_data_filling,
                prompt,
                received_context,
                {"type": "object", "properties": properties, "required": list(properties)},
                template_uri,
            )
            merged = dict(pending.validated_data)
            for name in pending.requested_fields:
                value = filled.data.get(name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Negotiation did not resolve required field: {name}")
                merged[name] = value
            invalid_fields = self._semantic_invalid_fields(merged)
            if invalid_fields:
                return self._failed_task(
                    context,
                    "Negotiation-T ACCEPT supplied data for the wrong target: "
                    + ", ".join(sorted(invalid_fields)),
                )
            logger.info(
                f"[{self.__class__.__name__}] Negotiation-T ACCEPT applied: "
                f"task_id={context.task_id}, fields={list(pending.requested_fields)}"
            )
            return await self._run_business(context, self._format_business_input(merged))
        if received_context.performative == NegotiationPerformative.REJECT:
            if template_uri != INFORMATION_NEGOTIATION_ACCEPT_REJECT_URI:
                raise ValueError(f"Unsupported Negotiation-T Reject template: {template_uri}")
            return self._failed_task(context, "Negotiation-T REJECT")
        if received_context.performative == NegotiationPerformative.ABORT:
            if template_uri != NEGOTIATION_ABORT_URI:
                raise ValueError(f"Unsupported Negotiation-T Abort template: {template_uri}")
            return self._failed_task(context, "Negotiation-T ABORT")
        raise ValueError("Expected Negotiation-T ACCEPT, REJECT, or ABORT")

    @staticmethod
    def _format_business_input(data: dict[str, object]) -> str:
        return "\n".join(f"{key}：{value}" for key, value in data.items())

    async def _run_business(self, context: RequestContext, user_input: str) -> Task:
        response = await asyncio.to_thread(
            self._execute_task, user_input, context.task_id, context.context_id
        )
        metadata = {TASK_T_EXTENSION_URI: response}
        return Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[Artifact(
                artifact_id=str(uuid.uuid4()),
                parts=[Part(text=response)],
                metadata=metadata,
            )],
            metadata=metadata,
        )

    @staticmethod
    def _failed_task(context: RequestContext, message: str) -> Task:
        return Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_FAILED),
            artifacts=[Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(text=message)])],
            metadata={},
        )

    async def _handle_authorization(
        self, context: RequestContext, event_queue: EventQueue, metadata: dict[str, Any]
    ) -> None:
        prompt = metadata.get(AUTHORIZATION_T_EXTENSION_URI)
        template_uri = metadata.get(TEMPLATE_URI_METADATA_KEY)
        if template_uri != AUTHORIZATION_POLICY_MANAGEMENT_URI:
            raise ValueError(f"Unsupported Authorization-T template: {template_uri}")
        await asyncio.to_thread(
            self.a2at_server.validate_auth_prompt_and_data_filling,
            prompt,
            AUTHORIZATION_SCHEMA,
            template_uri,
        )
        self._authorization_policy = str(prompt)
        logger.info(f"[{self.__class__.__name__}] Authorization-T policy accepted")
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            metadata={},
        ))

    async def _handle_notification_subscription(
        self, context: RequestContext, event_queue: EventQueue, metadata: dict[str, Any]
    ) -> None:
        prompt = metadata.get(NOTIFICATION_T_EXTENSION_URI)
        template_uri = metadata.get(TEMPLATE_URI_METADATA_KEY)
        if template_uri != SERVICE_RECOVERY_URI:
            raise ValueError(f"Unsupported Notification-T template: {template_uri}")
        await asyncio.to_thread(
            self.a2at_server.validate_notification_prompt_and_data_filling,
            prompt,
            NOTIFICATION_SCHEMA,
            template_uri,
        )
        logger.info(f"[{self.__class__.__name__}] Notification-T subscription accepted")
        task_id = context.task_id or ""
        notification_queue: queue_module.Queue[dict[str, Any] | None] = (
            queue_module.Queue()
        )
        with self._notification_lock:
            self._notification_subscribers[task_id] = notification_queue
            for pending_result in self._notification_backlog:
                notification_queue.put_nowait(dict(pending_result))
            self._notification_backlog.clear()
        acknowledgement_metadata = {
            NOTIFICATION_T_EXTENSION_URI: "Notification-T subscription established",
            TEMPLATE_URI_METADATA_KEY: template_uri,
        }
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            artifacts=[Artifact(
                artifact_id=str(uuid.uuid4()),
                name="notification-subscription",
                parts=[Part(text="Subscribed to recovery results")],
                metadata=acknowledgement_metadata,
            )],
            metadata=acknowledgement_metadata,
        ))
        try:
            while not self._shutdown:
                try:
                    result = await asyncio.to_thread(notification_queue.get, True, 2)
                except queue_module.Empty:
                    continue
                if result is None:
                    break
                result_json = json.dumps(result, ensure_ascii=False)
                result_metadata = {
                    NOTIFICATION_T_EXTENSION_URI: result_json,
                    TEMPLATE_URI_METADATA_KEY: SERVICE_RECOVERY_URI,
                }
                data_value = ParseDict(result, Value())
                await event_queue.enqueue_event(Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                    artifacts=[Artifact(
                        artifact_id=str(uuid.uuid4()),
                        name="recovery-result",
                        parts=[Part(data=data_value)],
                        metadata=result_metadata,
                    )],
                    metadata=result_metadata,
                ))
                break
        finally:
            with self._notification_lock:
                self._notification_subscribers.pop(task_id, None)

    def _execute_task(
        self, user_input: str, task_id: str | None = None, context_id: str | None = None
    ) -> str:
        prompt = self.prompt_template.format(task=user_input)
        _, response = self.llm.ask_llm(prompt)
        if not response:
            raise RuntimeError("The simulated business LLM returned no response")
        return response

    def push_notification_result(self, result: Mapping[str, Any]) -> None:
        """Broadcast one immutable business result to every active subscription."""
        snapshot = dict(result)
        with self._notification_lock:
            subscribers = tuple(self._notification_subscribers.values())
            if not subscribers:
                self._notification_backlog.append(snapshot)
                return
        for notification_queue in subscribers:
            notification_queue.put_nowait(dict(snapshot))

    def get_authorization_policy(self) -> str | None:
        return self._authorization_policy

    def shutdown(self) -> None:
        self._shutdown = True
        with self._notification_lock:
            subscribers = tuple(self._notification_subscribers.values())
        for notification_queue in subscribers:
            notification_queue.put_nowait(None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        self._pending.pop(task_id, None)
        with self._notification_lock:
            notification_queue = self._notification_subscribers.pop(task_id, None)
        if notification_queue is not None:
            notification_queue.put_nowait(None)
        logger.info(f"[{self.__class__.__name__}] Task cancelled: task_id={context.task_id}")
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
            metadata={},
        ))
