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

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from loguru import logger
from workflow_engine import (
    EventCallback,
    EventType,
    Workflow,
    execute_psop,
)

from host_agent.adapters import (
    AgentCardProvider,
    DefaultEngineClientFactory,
    EngineClientFactory,
    RegistryAgentCardProvider,
)
from host_agent.config import ControlPointContext, HostAgentConfig, RoleExecutionContext
from host_agent.dispatch_auth import DISPATCH_KEYS, PROOF_KEY, DispatchValidationError, verify_dispatch
from host_agent.execution import (
    HostExecutionTracker,
    host_event_state,
    host_final_state,
)
from host_agent.role_dispatch import (
    RoleDispatchEngineClient,
    ValidatingAuthProvider,
    project_dispatch_interfaces,
)
from host_agent.role_execution import RoleExecutionBridge
from host_agent.role_snapshot import read_role_snapshot, validated_agent_cards
from host_agent.utils import detect_language
from host_agent.workflow_repository import OrchestrationWorkflowRepository


class HostAgentEventCallback(EventCallback):
    """Log workflow timings without retaining request state on the executor."""

    def __init__(self):
        self._step_start_times: dict[str, float] = {}
        self._task_start_times: dict[str, float] = {}

    def on_event(self, event_type: str, data: dict[str, Any]):
        now = time.time()
        if event_type == EventType.STEP_START:
            step_name = data.get("step")
            self._step_start_times[step_name] = now
            logger.info(f"[Timing] Step '{step_name}' started")
        elif event_type == EventType.TASK_REQUEST:
            agent = data.get("agent", "?")
            step = data.get("step", "?")
            self._task_start_times[agent] = now
            logger.info(f"[Timing] Task dispatched to '{agent}' (step={step})")
        elif event_type == EventType.TASK_RESPONSE:
            agent = data.get("agent", "?")
            step = data.get("step", "?")
            elapsed = now - self._task_start_times.get(agent, now)
            logger.info(f"[Timing] Task response from '{agent}' (step={step}): {elapsed:.2f}s")
        elif event_type == EventType.STEP_COMPLETE:
            step_name = data.get("step")
            elapsed = now - self._step_start_times.get(step_name, now)
            logger.info(f"[Timing] Step '{step_name}' completed: {elapsed:.2f}s")

    def transform(self, event: dict) -> dict:
        self.on_event(event.get("type", ""), event.get("data", {}))
        return event


class HostAgentExecutor(AgentExecutor):
    """Protocol-neutral workflow execution host.

    Runtime owns transport, PSOP loading, event wrapping, and resource
    lifecycle. Business decisions are supplied through ``control_point_factory``.
    """

    def __init__(
        self,
        *,
        config: HostAgentConfig,
        control_point_factory: Callable[[ControlPointContext], Any],
        extension_lifecycle: Any | None = None,
        credentials_config: str | dict | None = None,
        workflow_repository: Any | None = None,
        agent_card_provider: AgentCardProvider | None = None,
        engine_client_factory: EngineClientFactory | None = None,
        auth_provider: Any | None = None,
    ) -> None:
        if control_point_factory is None:
            raise ValueError("control_point_factory is required")

        self._execution_tracker = HostExecutionTracker()
        self._config = config
        self._extension_lifecycle = extension_lifecycle
        self._control_point_factory = control_point_factory
        self._credentials_config = credentials_config
        self._auth_provider = auth_provider
        self._workflow_repository = workflow_repository or OrchestrationWorkflowRepository(
            orch_url=config.orchestration_url,
            ssl_verify=config.ssl_verify,
        )
        self._agent_card_provider = agent_card_provider or RegistryAgentCardProvider(
            config.registry_url,
            ssl_verify=config.ssl_verify,
        )
        self._engine_client_factory = engine_client_factory or DefaultEngineClientFactory(
            credentials_config=credentials_config,
            ssl_verify=config.ssl_verify,
            max_negotiation_exchanges=config.max_negotiation_exchanges,
        )

        logger.info(
            f"[HostAgent] Initialized: orch_url={config.orchestration_url}, "
            f"registry_url={config.registry_url}, ssl_verify={config.ssl_verify}"
        )

    async def start(self) -> None:
        if self._extension_lifecycle is not None:
            result = self._extension_lifecycle.start()
            if inspect.isawaitable(result):
                await result

    async def aclose(self) -> None:
        close = getattr(self._extension_lifecycle, "aclose", None)
        if close is not None:
            await close()

    def shutdown(self) -> None:
        stop = getattr(self._extension_lifecycle, "request_stop", None)
        if stop is not None:
            stop()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        started = time.time()
        intent = context.get_user_input()
        lang = detect_language(intent)
        task_id = context.task_id or "N/A"
        context_id = context.context_id or "N/A"
        logger.info(f"[HostAgent] execute: task_id={task_id}, context_id={context_id}, lang={lang}")

        terminal_event: dict | None = None
        event_count = 0
        self._execution_tracker.begin(context.task_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            metadata={},
        ))

        engine_client = None
        role_snapshot = None
        try:
            metadata = self._orchestration_metadata(context)
            role_dispatch = any(key in metadata for key in ("__orch_binding__", "__orch_cards__", PROOF_KEY))
            if role_dispatch:
                # Deployment admission first (REQ74 P4): a valid signature on a
                # closed deployment must not reach workflow verification.
                admitted, reasons = self._config.role_execution_admitted()
                if not admitted:
                    raise DispatchValidationError(
                        "Role execution is not admitted on this host",
                        reason="ROLE_EXECUTION_NOT_ADMITTED")
                verify_dispatch(metadata, self._config.role_dispatch_key, intent=intent)
            processed_intent = await self._process_intent(intent)
            try:
                workflow = await self._resolve_workflow(context, processed_intent)
            except (TypeError, ValueError) as exc:
                if role_dispatch:
                    raise DispatchValidationError("Invalid role execution workflow", reason="WORKFLOW_SCHEMA") from exc
                raise
            steps = workflow.get("steps", []) if isinstance(workflow, dict) else getattr(workflow, "steps", [])
            for step in steps:
                tasks = step.get("subtasks", []) if isinstance(step, dict) else getattr(step, "subtasks", [])
                if any((task.get("binding") if isinstance(task, dict) else getattr(task, "binding", None)) == "role" for task in tasks):
                    raise ValueError("ROLE_EXECUTION_NOT_ENABLED: unresolved role workflow")
            if role_dispatch:
                role_snapshot = read_role_snapshot(metadata, workflow)
            try:
                agent_cards = await self._load_agent_cards()
            except Exception as exc:
                if role_dispatch:
                    raise DispatchValidationError("Cannot refresh selected instance cards", reason="REGISTRY_UNAVAILABLE") from exc
                raise
            role_context = None
            role_bridge = None
            if role_snapshot is not None:
                agent_cards = validated_agent_cards(role_snapshot, agent_cards)
                role_context = RoleExecutionContext(
                    execution_id=role_snapshot.execution_id,
                    caller_id=role_snapshot.context.caller_id,
                    scope=role_snapshot.context.scope,
                    bindings=tuple(binding.model_copy(deep=True) for binding in role_snapshot.bindings),
                )
                role_bridge = RoleExecutionBridge(role_context, workflow)
                role_context = role_bridge.context
                logger.info(
                    "[RoleHost] accepted execution_id={} psop_id={} caller_id={!r} scope={!r} task_ids={} instance_ids={}",
                    role_snapshot.execution_id, role_snapshot.template["id"],
                    role_snapshot.context.caller_id, role_snapshot.context.scope.as_path(),
                    [binding.task_id for binding in role_snapshot.bindings],
                    [card.instance_id for card in role_snapshot.cards],
                )
            dispatch_cards = agent_cards
            dispatch_provider = None
            if role_snapshot is not None:
                dispatch_cards = project_dispatch_interfaces(role_snapshot, agent_cards)
                user_provider = getattr(self, "_auth_provider", None)
                if user_provider is not None:
                    dispatch_provider = ValidatingAuthProvider(
                        user_provider,
                        execution_id=role_snapshot.execution_id,
                        custom_headers=getattr(self._config, "custom_auth_headers", ()),
                        credentials=getattr(self, "_credentials_config", None),
                    )
            engine_client = self._engine_client_factory.create(
                dispatch_cards,
                **({"auth_provider": dispatch_provider} if dispatch_provider is not None else {}),
            )
            if role_snapshot is not None:
                engine_client = RoleDispatchEngineClient(
                    engine_client, role_context, role_snapshot,
                    credentials=getattr(self, "_credentials_config", None),
                    auth_provider=getattr(self, "_auth_provider", None),
                )
            control_point = self._control_point_factory(ControlPointContext(
                orchestration_url=self._config.orchestration_url,
                ssl_verify=self._config.ssl_verify,
                lang=lang,
                role_execution=role_context,
            ))
            event_tracker = HostAgentEventCallback()
            if role_bridge is not None:
                control_point = role_bridge.wrap(control_point)

            def on_event(event):
                if role_bridge is not None:
                    role_bridge.observe(event)
                return event_tracker.transform(event)

            execution_started = time.time()
            async for event in execute_psop(
                psop=Workflow.from_dict(workflow) if role_snapshot is not None else workflow,
                agent_cards=dispatch_cards,
                control_point=control_point,
                engine_client=engine_client,
                runtime_intent=processed_intent,
                lang=lang,
                ssl_verify=self._config.ssl_verify,
                on_event=on_event,
            ):
                event_count += 1
                if event.get("type") in {"complete", "error"}:
                    terminal_event = event
                await event_queue.enqueue_event(
                    self._event_to_task_update(event, context, lang)
                )
            logger.info(
                f"[HostAgent] Workflow execution done ({time.time() - execution_started:.2f}s), "
                f"{event_count} events"
            )

            await event_queue.enqueue_event(Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=host_final_state([terminal_event] if terminal_event else [])),
                metadata={},
            ))
            logger.info(f"[HostAgent] Total execute time: {time.time() - started:.2f}s")
        except asyncio.CancelledError:
            return
        except DispatchValidationError as exc:
            error_data = exc.event_data()
            if role_snapshot is not None:
                error_data["execution_id"] = role_snapshot.execution_id
            logger.warning(
                "[RoleHost] rejected task_id={} execution_id={} caller_id={!r} scope={!r} "
                "code={} reason={} diagnostic_reason={} task_ids={} instance_id={}",
                task_id, role_snapshot.execution_id if role_snapshot else "unverified",
                role_snapshot.context.caller_id if role_snapshot else "unverified",
                role_snapshot.context.scope.as_path() if role_snapshot else "unverified",
                exc.code, exc.reason, exc.diagnostic_reason, exc.task_ids, exc.instance_id,
            )
            await event_queue.enqueue_event(self._event_to_task_update({"type": "error", "data": error_data}, context, lang))
        except Exception as exc:
            logger.error(f"[HostAgent] Failed: {exc}", exc_info=True)
            await event_queue.enqueue_event(self._error_task(context, str(exc), lang))
        finally:
            self._execution_tracker.end(context.task_id)
            if engine_client is not None:
                with suppress(Exception):
                    await engine_client.close()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info(f"[HostAgent] Task cancelled: task_id={context.task_id}")
        self._execution_tracker.cancel(context.task_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
            metadata={},
        ))

    @staticmethod
    def _orchestration_metadata(context: RequestContext) -> dict[str, Any]:
        """Read orchestration context from request or message metadata."""
        metadata = dict(context.metadata or {})
        incoming = context.message
        if incoming is not None and getattr(incoming, "metadata", None):
            try:
                from google.protobuf.json_format import MessageToDict

                message_metadata = MessageToDict(incoming.metadata) or {}
                for key, value in message_metadata.items():
                    if key in (*DISPATCH_KEYS, PROOF_KEY) and key in metadata and metadata[key] != value:
                        raise DispatchValidationError("Conflicting orchestration metadata", reason="METADATA_CONFLICT")
                    metadata.setdefault(key, value)
            except DispatchValidationError:
                raise
            except Exception:
                pass
        return metadata

    async def _process_intent(self, intent: str) -> str:
        return intent

    async def _resolve_workflow(self, context: RequestContext, intent: str):
        metadata = self._orchestration_metadata(context)
        psop_id = metadata.get("__orch_psop_id__")
        if "__orch_psop_id__" in metadata and (not isinstance(psop_id, str) or not psop_id.strip()):
            raise ValueError("Explicit PSOP ID must be a non-empty string")
        if "__orch_psop__" in metadata:
            logger.info("[HostAgent] Using PSOP snapshot from orchestration center")
            psop_snapshot = metadata["__orch_psop__"]
            if isinstance(psop_snapshot, str):
                psop_snapshot = json.loads(psop_snapshot)
            if not isinstance(psop_snapshot, dict):
                raise ValueError("Explicit PSOP snapshot must be an object")
            snapshot_id = psop_snapshot.get("id")
            if not isinstance(snapshot_id, str) or not snapshot_id.strip():
                raise ValueError("Explicit PSOP snapshot must contain an ID")
            if psop_id is not None and snapshot_id != psop_id:
                raise ValueError("Explicit PSOP snapshot ID does not match requested ID")
            if not isinstance(psop_snapshot.get("steps"), list):
                raise ValueError("Explicit PSOP snapshot must contain a steps list")
            # Use the SDK's actual wire parser; never fall back to another
            # workflow when explicitly supplied execution metadata is invalid.
            Workflow.from_dict(psop_snapshot)
            return deepcopy(psop_snapshot)

        if psop_id is not None:
            logger.info(f"[HostAgent] Using psop_id from orchestration center: {psop_id}")
            workflow = await self._workflow_repository.get(psop_id)
            loaded_id = workflow.get("id") if isinstance(workflow, dict) else getattr(workflow, "id", None)
            if loaded_id != psop_id:
                raise ValueError("Loaded PSOP ID does not match requested ID")
            return workflow

        return await self._workflow_repository.find(intent)

    async def _load_agent_cards(self) -> list:
        cards = await self._agent_card_provider.load()
        logger.info(f"[HostAgent] Loaded {len(cards)} agent cards from registry")
        return cards

    def _event_to_task_update(self, event: dict, context: RequestContext, lang: str):
        """Wrap one SDK event into an A2A-T status update."""
        event_type = event.get("type", "")
        data = event.get("data", {})
        metadata = {"__sdk_event__": json.dumps(event, ensure_ascii=False, default=str)}
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(
                state=host_event_state(event_type),
                message=Message(
                    role=2,
                    parts=[Part(text=self._event_summary(event_type, data, lang))],
                ),
            ),
            metadata=metadata,
        )

    def _event_summary(self, event_type: str, data: dict, lang: str) -> str:
        zh = lang == "zh"
        summaries = {
            "start": (
                f"工作流开始: {data.get('workflow', '')}"
                if zh else
                f"Workflow started: {data.get('workflow', '')}"
            ),
            "step_start": (
                f"步骤开始: {data.get('step', '')}" if zh else f"Step started: {data.get('step', '')}"
            ),
            "agent_request": f"-> {data.get('agent', '')}",
            "agent_response": f"<- {data.get('agent', '')}",
            "route_decision": (
                f"路由: {data.get('step', '')} -> {data.get('next', '')}"
                if zh else
                f"Route: {data.get('step', '')} -> {data.get('next', '')}"
            ),
            "step_complete": (
                f"步骤完成: {data.get('step', '')}" if zh else f"Step completed: {data.get('step', '')}"
            ),
            "task_status_changed": (
                f"状态: {data.get('status', '')}" if zh else f"Status: {data.get('status', '')}"
            ),
            "negotiation_request": (
                f"协商请求: {data.get('agent', '')}" if zh else f"Negotiation request: {data.get('agent', '')}"
            ),
            "negotiation_resolved": (
                f"协商解决: {data.get('agent', '')}" if zh else f"Negotiation resolved: {data.get('agent', '')}"
            ),
            "negotiation_failed": (
                f"协商失败: {data.get('agent', '')}" if zh else f"Negotiation failed: {data.get('agent', '')}"
            ),
            "authorization_request": (
                f"授权请求: {data.get('agent', '')}" if zh else f"Authorization request: {data.get('agent', '')}"
            ),
            "notification": f"通知: {data.get('agent', '')}" if zh else f"Notification: {data.get('agent', '')}",
            "complete": "工作流执行完成" if zh else "Workflow execution complete",
            "error": f"错误: {data.get('error', '')}" if zh else f"Error: {data.get('error', '')}",
            "close": "流已结束" if zh else "Stream closed",
        }
        return summaries.get(event_type, event_type)

    def _error_task(
        self,
        context: RequestContext,
        error_msg: str,
        lang: str,
    ) -> TaskStatusUpdateEvent:
        prefix = "错误" if lang == "zh" else "Error"
        data = {"error": error_msg}
        code = error_msg.split(":", 1)[0]
        if code in {"INSTANCE_SNAPSHOT_MISMATCH", "ROLE_EXECUTION_NOT_ENABLED"}:
            data["code"] = code
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_FAILED,
                message=Message(role=2, parts=[Part(text=f"{prefix}: {error_msg}")]),
            ),
            metadata={"__sdk_event__": json.dumps(
                {"type": "error", "data": data},
                ensure_ascii=False,
            )},
        )
