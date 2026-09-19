from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Callable
from contextlib import suppress
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
    A2ATransport,
    EventCallback,
    EventType,
    RegistryClient,
    WorkflowEngineClient,
    execute_psop,
)

from common.util.config_util import get_conf
from host_agent.execution import (
    HostExecutionTracker,
    host_event_state,
    host_final_state,
)
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
        extension_agent_cards: list | None = None,
    control_point_factory: Callable[..., Any] | None = None,
    extension_lifecycle: Any | None = None,
    credentials_config: str | dict | None = None,
    workflow_repository: Any | None = None,
    ) -> None:
        if control_point_factory is None:
            raise ValueError("control_point_factory is required")

        self._execution_tracker = HostExecutionTracker()
        self._ssl_verify = str(get_conf().get("client_verify_server", "false")).lower() == "true"
        orch_port = get_conf().get("port", "5001")
        self._orch_url = f"https://127.0.0.1:{orch_port}"
        registry_url = get_conf().get("agent_registry_url", None)
        self._registry_url = registry_url or "https://127.0.0.1:5000"
        self._credentials_config = credentials_config
        self._extension_agent_cards = extension_agent_cards or []
        self._extension_lifecycle = extension_lifecycle
        self._control_point_factory = control_point_factory
        self._workflow_repository = workflow_repository or OrchestrationWorkflowRepository(
            orch_url=self._orch_url,
            ssl_verify=self._ssl_verify,
        )

        logger.info(
            f"[HostAgent] Initialized: orch_url={self._orch_url}, "
            f"registry_url={self._registry_url}, ssl_verify={self._ssl_verify}"
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
        logger.info(
            f"[HostAgent] execute: task_id={task_id}, context_id={context_id}, "
            f"lang={lang}, intent={intent[:100]}"
        )

        collected_events: list[dict] = []
        self._execution_tracker.begin(context.task_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            metadata={},
        ))

        engine_client = None
        try:
            processed_intent = await self._process_intent(intent)
            workflow = await self._resolve_workflow(context, processed_intent)
            agent_cards = await self._load_agent_cards()
            transport = A2ATransport(
                agent_cards=agent_cards,
                credentials_config=self._credentials_config,
                ssl_verify=self._ssl_verify,
            )
            engine_client = WorkflowEngineClient.owning(
                transport,
                max_negotiation_exchanges=3,
            )
            control_point = self._control_point_factory(
                orch_url=self._orch_url,
                ssl_verify=self._ssl_verify,
                lang=lang,
            )
            event_tracker = HostAgentEventCallback()

            execution_started = time.time()
            async for event in execute_psop(
                psop=workflow,
                agent_cards=agent_cards,
                control_point=control_point,
                engine_client=engine_client,
                runtime_intent=processed_intent,
                lang=lang,
                ssl_verify=self._ssl_verify,
                on_event=event_tracker.transform,
            ):
                collected_events.append(event)
                await event_queue.enqueue_event(
                    self._event_to_task_update(event, context, lang)
                )
            logger.info(
                f"[HostAgent] Workflow execution done ({time.time() - execution_started:.2f}s), "
                f"{len(collected_events)} events"
            )

            await event_queue.enqueue_event(Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=host_final_state(collected_events)),
                metadata={
                    "__sdk_events__": json.dumps(
                        collected_events, ensure_ascii=False, default=str
                    )
                },
            ))
            logger.info(f"[HostAgent] Total execute time: {time.time() - started:.2f}s")
        except asyncio.CancelledError:
            return
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

                for key, value in (MessageToDict(incoming.metadata) or {}).items():
                    metadata.setdefault(key, value)
            except Exception:
                pass
        return metadata

    async def _process_intent(self, intent: str) -> str:
        return intent

    async def _resolve_workflow(self, context: RequestContext, intent: str):
        metadata = self._orchestration_metadata(context)
        psop_snapshot = metadata.get("__orch_psop__")
        if psop_snapshot:
            logger.info("[HostAgent] Using PSOP snapshot from orchestration center")
            if isinstance(psop_snapshot, str):
                psop_snapshot = json.loads(psop_snapshot)
            return psop_snapshot

        psop_id = metadata.get("__orch_psop_id__")
        if psop_id:
            logger.info(f"[HostAgent] Using psop_id from orchestration center: {psop_id}")
            return await self._workflow_repository.get(psop_id)

        return await self._workflow_repository.find(intent)

    async def _load_agent_cards(self) -> list:
        registry = RegistryClient(self._registry_url, ssl_verify=self._ssl_verify)
        cards = await registry.fetch_agent_cards()
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
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_FAILED,
                message=Message(role=2, parts=[Part(text=f"{prefix}: {error_msg}")]),
            ),
            metadata={"__sdk_event__": json.dumps(
                {"type": "error", "data": {"error": error_msg}},
                ensure_ascii=False,
            )},
        )
