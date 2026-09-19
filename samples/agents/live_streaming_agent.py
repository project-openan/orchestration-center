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
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Live Streaming Agent -- workflow execution host for live broadcast assurance.

Leader role: receives the raw intent via A2A-T, searches/loads the PSOP
workflow from the orchestration center, then executes the workflow via
the workflow-engine SDK (execute_psop), streaming SDK events back to the
caller as A2A-T TaskUpdate events.

SelfLoop steps (step1, step4, step7) are executed locally via LLM.
Other steps are dispatched to Service Assurance Agent / Wireless Domain Agent via A2A-T.
No Authorization-T or Notification-T pre-positioning.
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

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
from a2a_t.negotiation.content import NegotiationItem
from loguru import logger
from workflow_engine import (
    A2atMessages,
    A2ATransport,
    ControlPoint,
    MessageContent,
    NegotiationReply,
    RegistryClient,
    RouteDecision,
    TaskResult,
    WorkflowEngineClient,
    execute_psop,
    load_psop,
    search_psop,
)

from common.llm import get_llm_instance
from common.util.config_util import get_conf
from samples.agents.host_execution import (
    HostExecutionTracker,
    host_event_state,
    host_final_state,
)
from samples.spn_host_agent.content import (
    INFORMATION_NEGOTIATION_PROPOSE_URI,
    NEGOTIATION_ITEMS_SCHEMA,
    create_a2at_client,
    negotiation_abort_content,
    negotiation_accept_content,
    negotiation_prompt,
    negotiation_reject_content,
)
from samples.agents.util.negotiation_utils import detect_lang


class LiveStreamingControlPoint(ControlPoint):
    """ControlPoint for Live Streaming Agent workflow execution.

    SelfLoop steps are executed locally via LLM (event info parsing,
    KQI monitoring). Other steps are dispatched to remote agents.
    """

    _llm_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ls_llm_")
    _NEGOTIATION_MAX_ROUNDS = 3

    def __init__(
        self,
        orch_url: str,
        ssl_verify: bool = False,
        lang: str = "zh",
    ):
        self.orch_url = orch_url.rstrip("/")
        self.ssl_verify = ssl_verify
        self.lang = lang or "zh"
        self.llm_client = get_llm_instance()
        self.a2at_client = create_a2at_client()

    async def on_task(self, request) -> MessageContent:
        return MessageContent.text(request.instruction)

    async def on_self_task(self, request) -> TaskResult:
        try:
            result = await self._llm_execute_task(request.instruction, request.workflow_input)
            return TaskResult.succeeded((result,))
        except Exception as e:
            err = f"Self-loop task failed : {str(e)}"
            logger.error(f"  >Self-loop failed: {request.instruction[:60]} | Error: {err}")
            return TaskResult.failed("self_task.failed", err)

    async def on_route(self, request) -> RouteDecision:
        allowed = await self._llm_route_condition(request)
        if allowed:
            return RouteDecision.allow("edge condition satisfied")
        return RouteDecision.deny("edge condition not satisfied")

    async def on_negotiation(self, request) -> NegotiationReply:
        context = A2atMessages.negotiation_context(request.received)
        prompt, template_uri = negotiation_prompt(request.received)
        if template_uri != INFORMATION_NEGOTIATION_PROPOSE_URI:
            return NegotiationReply.send(
                await asyncio.to_thread(
                    negotiation_abort_content,
                    self.a2at_client,
                    context,
                    f"Unsupported negotiation template: {template_uri}",
                )
            )
        try:
            filled = await asyncio.to_thread(
                self.a2at_client.validate_propose_prompt_and_data_filling,
                prompt,
                context,
                NEGOTIATION_ITEMS_SCHEMA,
                template_uri,
            )
        except Exception as error:
            return NegotiationReply.send(
                await asyncio.to_thread(
                    negotiation_abort_content,
                    self.a2at_client,
                    context,
                    f"Cannot validate negotiation proposal: {error}",
                )
            )
        requested = filled.data.get("items")
        if not isinstance(requested, (list, tuple)) or not requested:
            return NegotiationReply.send(
                await asyncio.to_thread(
                    negotiation_reject_content,
                    self.a2at_client,
                    context,
                    "No requested fields were extracted",
                )
            )
        available = {
            "SLA授权方案": (
                "授权在直播核心保障小区保留SLA优先级，非核心小区按负载分级节能；"
                "当下行PRB利用率超过70%或端到端时延超过20ms时立即退出节能。"
            )
        }
        answers: list[NegotiationItem] = []
        for requested_name in requested:
            name = str(requested_name).strip()
            value = available.get(name)
            if value is None:
                return NegotiationReply.send(
                    await asyncio.to_thread(
                        negotiation_reject_content,
                        self.a2at_client,
                        context,
                        f"Cannot supply field: {name}",
                    )
                )
            answers.append(NegotiationItem(name, value))
        return NegotiationReply.send(
            await asyncio.to_thread(
                negotiation_accept_content,
                self.a2at_client,
                context,
                answers,
                "补充SLA授权方案",
            )
        )

    async def _llm_execute_task(self, message: str, workflow_input) -> str:
        context = self._format_workflow_input(workflow_input)
        lang_hint = "请用中文回复。" if self.lang == "zh" else "Respond in English."
        prompt = f"""# Role
You are the Live Streaming Agent for event live broadcast assurance, responsible for event requirement parsing and real-time KQI monitoring.

# Execution Results of Completed Steps
{context or "(this is the first step, no completed predecessor steps yet)"}

# Current Task
{message}

# Output Requirements
- Based on the task description and available context, generate concrete data fitting a telecom live-broadcast assurance scenario.
- Output a structured analysis result with concrete values, times, locations, etc.
- Data must be realistic and consistent with an actual 5G live-broadcast assurance scenario.
{lang_hint}"""
        if not self.llm_client:
            if self.lang == "zh":
                return f"Live Streaming Agent 执行完成: {message[:100]}"
            return f"Live Streaming Agent execution done: {message[:100]}"
        try:
            t0 = time.time()
            logger.info("[LiveStreamingCP] Self-loop task: calling LLM...")
            _, result = await asyncio.get_event_loop().run_in_executor(
                self._llm_executor, self.llm_client.ask_llm, prompt
            )
            logger.info(f"[LiveStreamingCP] Self-loop task: done ({time.time()-t0:.2f}s)")
            return result.strip() if result else ""
        except Exception as e:
            logger.error(f"[LiveStreamingCP] LLM self-loop task failed: {e}")
            if self.lang == "zh":
                return f"Live Streaming Agent 执行完成（LLM不可用）: {message[:200]}"
            return f"Live Streaming Agent execution done (LLM unavailable): {message[:200]}"

    @staticmethod
    def _format_workflow_input(workflow_input) -> str:
        parts = []
        if workflow_input.runtime_intent:
            parts.append(f"Runtime intent: {workflow_input.runtime_intent}")
        for upstream in workflow_input.upstream_results:
            parts.append(f"### {upstream.step_name}")
            for result in upstream.task_results:
                parts.append(
                    f"- Agent: {result.agent_name}; skill: {result.skill}; "
                    f"status: {result.status.value}"
                )
                for output in result.outputs:
                    parts.append(f"  Output: {output}")
                if result.error:
                    parts.append(f"  Error: {result.error}")
        return "\n".join(parts) if parts else "(no upstream workflow input)"

    async def _llm_route_condition(self, request) -> bool:
        results_context = []
        for result in request.current_results:
            outputs = "\n".join(str(output) for output in result.outputs)
            results_context.append(
                f"Agent: {result.agent_name}\n"
                f"Status: {result.status.value}\n"
                f"Outputs:\n{outputs or '(none)'}\n"
                f"Error: {result.error or '(none)'}"
            )
        results_text = "\n\n".join(results_context) or "(no task results)"
        prompt_template = f"""
# Role
You are a workflow edge-condition evaluator.

# Current Context
Current step: {request.step_name}
Candidate next step: {request.next_step}

# Current Step Results
{results_text}

# Condition To Evaluate
{request.condition}

# Decision Logic
Evaluate only this candidate edge. Other outgoing edges are evaluated independently.
Return true only when the condition is supported by the results; otherwise return false.

# Output Format
- Output exactly one lowercase word: true or false.
- Do not output an explanation or punctuation.
"""
        if not self.llm_client:
            logger.error("LLM client is not initialized; denying conditional edge")
            return False
        try:
            t0 = time.time()
            logger.info(
                f"[LiveStreamingCP] Evaluating route {request.step_name} -> "
                f"{request.next_step}: calling LLM..."
            )
            _, decision = await asyncio.get_event_loop().run_in_executor(
                self._llm_executor, self.llm_client.ask_llm, prompt_template
            )
            normalized = (decision or "").strip().lower().strip("` .")
            logger.info(
                f"[LiveStreamingCP] Route {request.step_name} -> {request.next_step} "
                f"evaluated as '{normalized}' ({time.time()-t0:.2f}s)"
            )
            if normalized == "true":
                return True
            if normalized != "false":
                logger.warning(
                    f"Unexpected route decision '{decision}'; denying conditional edge"
                )
            return False
        except Exception as e:
            logger.error(f"[LiveStreamingCP] Conditional route evaluation failed: {e}")
            return False


class LiveStreamingAgentExecutor(AgentExecutor):
    """Live Streaming Agent -- workflow execution host for live broadcast assurance.

    Receives the raw intent, searches/loads the PSOP workflow, then executes
    it via the workflow-engine SDK. SelfLoop steps are handled locally via LLM,
    other steps are dispatched to Assurance/Wireless Domain Agents via A2A-T.
    No Authorization-T or Notification-T pre-positioning.
    """

    def __init__(self) -> None:
        self._execution_tracker = HostExecutionTracker()
        self._ssl_verify = str(get_conf().get("client_verify_server", "false")).lower() == "true"

        orch_port = get_conf().get("port", "5001")
        self._orch_url = f"https://127.0.0.1:{orch_port}"

        registry_url = get_conf().get("agent_registry_url", None)
        self._registry_url = registry_url or "https://127.0.0.1:5000"

        self._cred_path = str(
            Path(__file__).resolve().parent.parent / "agent_credentials.json"
        )

        logger.info(
            f"[LiveStreamingAgent] Initialized: orch_url={self._orch_url}, "
            f"registry_url={self._registry_url}, ssl_verify={self._ssl_verify}"
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        t_execute = time.time()
        intent = context.get_user_input()
        lang = detect_lang(intent)
        task_id = context.task_id or "N/A"
        ctx_id = context.context_id or "N/A"
        logger.info(f"[LiveStreamingAgent] execute: task_id={task_id}, context_id={ctx_id}, lang={lang}, intent={intent[:100]}")

        collected_events = []
        self._execution_tracker.begin(context.task_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            metadata={},
        ))

        engine_client = None
        try:
            request_metadata = context.metadata or {}
            psop_id = request_metadata.get("__orch_psop_id__")
            if psop_id:
                logger.info(f"[LiveStreamingAgent] Using psop_id from metadata: {psop_id}")
            else:
                t0 = time.time()
                psop_id = await self._search_psop(intent)
                logger.info(f"[LiveStreamingAgent] PSOP search done ({time.time()-t0:.2f}s)")

            t0 = time.time()
            workflow = await self._load_psop(psop_id)
            logger.info(f"[LiveStreamingAgent] PSOP load done ({time.time()-t0:.2f}s)")

            t0 = time.time()
            agent_cards = await self._load_agent_cards()
            logger.info(f"[LiveStreamingAgent] Agent cards load done: {len(agent_cards)} cards ({time.time()-t0:.2f}s)")

            transport = A2ATransport(
                agent_cards=agent_cards,
                credentials_config=self._cred_path,
                ssl_verify=self._ssl_verify,
            )
            engine_client = WorkflowEngineClient.owning(
                transport,
                max_negotiation_exchanges=3,
            )

            cp = LiveStreamingControlPoint(
                orch_url=self._orch_url,
                ssl_verify=self._ssl_verify,
                lang=lang,
            )

            t0 = time.time()
            logger.info("[LiveStreamingAgent] Starting workflow execution")
            async for event in execute_psop(
                psop=workflow,
                agent_cards=agent_cards,
                control_point=cp,
                engine_client=engine_client,
                runtime_intent=intent,
                lang=lang,
                ssl_verify=self._ssl_verify,
            ):
                collected_events.append(event)
                task_update = self._event_to_task_update(event, context, lang)
                await event_queue.enqueue_event(task_update)
            logger.info(f"[LiveStreamingAgent] Workflow execution done ({time.time()-t0:.2f}s), {len(collected_events)} events")

            await event_queue.enqueue_event(Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=host_final_state(collected_events)),
                metadata={"__sdk_events__": json.dumps(collected_events, ensure_ascii=False, default=str)},
            ))
            logger.info(f"[LiveStreamingAgent] Total execute time: {time.time()-t_execute:.2f}s")

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[LiveStreamingAgent] Failed: {e}", exc_info=True)
            await event_queue.enqueue_event(self._error_task(context, str(e), lang))
        finally:
            self._execution_tracker.end(context.task_id)
            if engine_client is not None:
                with suppress(Exception):
                    await engine_client.close()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info(f"[LiveStreamingAgent] Task cancelled: task_id={context.task_id}")
        self._execution_tracker.cancel(context.task_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
            metadata={},
        ))

    async def _search_psop(self, intent: str) -> str:
        results = await search_psop(self._orch_url, intent, top_n=3, ssl_verify=self._ssl_verify)
        if results:
            logger.info(f"[LiveStreamingAgent] Found PSOP: {results[0].workflow_id}")
            return results[0].workflow_id
        raise RuntimeError("No matching workflow found")

    async def _load_psop(self, psop_id: str):
        workflow = await load_psop(self._orch_url, psop_id, ssl_verify=self._ssl_verify)
        logger.info(f"[LiveStreamingAgent] Loaded PSOP: {workflow.name} ({len(workflow.steps)} steps)")
        return workflow

    async def _load_agent_cards(self) -> list:
        registry = RegistryClient(self._registry_url, ssl_verify=self._ssl_verify)
        cards = await registry.fetch_agent_cards()
        logger.info(f"[LiveStreamingAgent] Loaded {len(cards)} agent cards from registry")
        return cards

    def _event_to_task_update(
        self,
        event: dict,
        context: RequestContext,
        lang: str,
    ):
        etype = event.get("type", "")
        data = event.get("data", {})
        summary = self._event_summary(etype, data, lang)
        metadata = {"__sdk_event__": json.dumps(event, ensure_ascii=False, default=str)}

        state = host_event_state(etype)
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(
                state=state,
                message=Message(role=2, parts=[Part(text=summary)]),
            ),
            metadata=metadata,
        )

    def _event_summary(self, etype: str, data: dict, lang: str) -> str:
        zh = lang == "zh"
        if etype == "start":
            wf_name = data.get("workflow", "")
            if zh:
                return f"工作流开始: {wf_name}" if wf_name else "工作流开始"
            return f"Workflow started: {wf_name}" if wf_name else "Workflow started"
        if etype == "step_start":
            return f"步骤开始: {data.get('step', '')}" if zh else f"Step started: {data.get('step', '')}"
        if etype == "agent_request":
            return f"-> {data.get('agent', '')}"
        if etype == "agent_response":
            return f"<- {data.get('agent', '')}"
        if etype == "route_decision":
            return f"路由: {data.get('step', '')} -> {data.get('next', '')}" if zh else f"Route: {data.get('step', '')} -> {data.get('next', '')}"
        if etype == "step_complete":
            return f"步骤完成: {data.get('step', '')}" if zh else f"Step completed: {data.get('step', '')}"
        if etype == "task_status_changed":
            return f"状态: {data.get('status', '')}" if zh else f"Status: {data.get('status', '')}"
        if etype == "negotiation_request":
            return f"协商请求: {data.get('agent', '')}" if zh else f"Negotiation request: {data.get('agent', '')}"
        if etype == "negotiation_resolved":
            return f"协商解决: {data.get('agent', '')}" if zh else f"Negotiation resolved: {data.get('agent', '')}"
        if etype == "negotiation_failed":
            return f"协商失败: {data.get('agent', '')}" if zh else f"Negotiation failed: {data.get('agent', '')}"
        if etype == "complete":
            return "工作流执行完成" if zh else "Workflow execution complete"
        if etype == "error":
            return f"错误: {data.get('error', '')}" if zh else f"Error: {data.get('error', '')}"
        if etype == "close":
            return "流结束" if zh else "Stream closed"
        return etype

    def _error_task(
        self,
        context: RequestContext,
        error_msg: str,
        lang: str,
    ) -> TaskStatusUpdateEvent:
        err_prefix = "错误" if lang == "zh" else "Error"
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_FAILED,
                message=Message(role=2, parts=[Part(text=f"{err_prefix}: {error_msg}")]),
            ),
            metadata={"__sdk_event__": json.dumps(
                {"type": "error", "data": {"error": error_msg}}, ensure_ascii=False
            )},
        )
