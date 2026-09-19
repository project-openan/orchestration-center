from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from a2a_t.negotiation.content import NegotiationItem
from loguru import logger
from samples.spn_host_agent.content import (
    INFORMATION_NEGOTIATION_PROPOSE_URI,
    NEGOTIATION_ITEMS_SCHEMA,
    complaint_data,
    create_a2at_client,
    negotiation_abort_content,
    negotiation_accept_content,
    negotiation_prompt,
    negotiation_reject_content,
    task_content,
)
from workflow_engine import (
    A2atMessages,
    ControlPoint,
    MessageContent,
    NegotiationReply,
    RouteDecision,
    TaskResult,
)

from common.llm import get_llm_instance


class SpnControlPoint(ControlPoint):
    """SPN host ControlPoint: routing, negotiation, and local merge policy."""

    _llm_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wb_llm_")
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
        """Generate final Task-T business content; the engine sends the envelope."""
        try:
            return await asyncio.to_thread(task_content, self.a2at_client, request)
        except Exception as exc:
            logger.error(f"[ControlPoint] Task-T generation failed for {request.step_name}: {exc}")
            raise

    async def on_self_task(self, request) -> TaskResult:
        """Handle a SelfLoop step locally through the LLM merge policy."""
        try:
            result = await self._llm_merge(request.instruction, request.workflow_input)
            return TaskResult.succeeded((result,))
        except Exception as exc:
            error = f"Self-loop task failed : {exc}"
            logger.error(
                f"  >Self-loop failed: {request.instruction[:60]} | Error: {error}"
            )
            return TaskResult.failed("self_task.failed", error)

    async def on_route(self, request) -> RouteDecision:
        """Evaluate exactly one conditional edge supplied by the engine."""
        allowed = await self._llm_route_condition(request)
        if allowed:
            return RouteDecision.allow("edge condition satisfied")
        return RouteDecision.deny("edge condition not satisfied")

    async def on_negotiation(self, request) -> NegotiationReply:
        """Validate the proposal and return a Negotiation-T accept or ending."""
        context = A2atMessages.negotiation_context(request.received)
        prompt, template_uri = negotiation_prompt(request.received)
        if template_uri != INFORMATION_NEGOTIATION_PROPOSE_URI:
            reason = f"Unsupported negotiation template: {template_uri}"
            return NegotiationReply.send(
                await asyncio.to_thread(
                    negotiation_abort_content,
                    self.a2at_client,
                    context,
                    reason,
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
            reason = f"Cannot validate negotiation proposal: {error}"
            return NegotiationReply.send(
                await asyncio.to_thread(
                    negotiation_abort_content,
                    self.a2at_client,
                    context,
                    reason,
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

        source = complaint_data(request.task)
        answers = []
        for field_name in requested:
            name = str(field_name).strip()
            value = source.get(name)
            if not isinstance(value, str) or not value.strip():
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
                "补充诊断信息",
            )
        )

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
            started = time.time()
            logger.info(
                f"[ControlPoint] Evaluating route {request.step_name} -> "
                f"{request.next_step}: calling LLM..."
            )
            _, decision = await asyncio.get_event_loop().run_in_executor(
                self._llm_executor, self.llm_client.ask_llm, prompt_template
            )
            normalized = (decision or "").strip().lower().strip("` .")
            logger.info(
                f"[ControlPoint] Route {request.step_name} -> {request.next_step} "
                f"evaluated as '{normalized}' ({time.time() - started:.2f}s)"
            )
            if normalized == "true":
                return True
            if normalized != "false":
                logger.warning(
                    f"Unexpected route decision '{decision}'; denying conditional edge"
                )
            return False
        except Exception as exc:
            logger.error(f"Conditional route evaluation failed: {exc}")
            return False

    async def _llm_merge(self, message: str, workflow_input) -> str:
        """LLM merge for local aggregation steps."""
        context = self._format_workflow_input(workflow_input)
        lang_hint = "Respond in Chinese." if self.lang == "zh" else "Respond in English."
        prompt = f"""# Role
        You are the SPN host agent performing a self-loop (local processing) task.
Analyze the available execution context and produce a comprehensive result.

# Execution Context (completed steps and their outputs)
{context}

# Task
{message}

# Output
Produce a clear, structured analysis based on the context above. {lang_hint}"""
        try:
            logger.info("[SPN ControlPoint] Self-loop merge: calling LLM...")
            _, result = await asyncio.get_event_loop().run_in_executor(
                self._llm_executor, self.llm_client.ask_llm, prompt
            )
            if result:
                logger.info(f"[SPN ControlPoint] Self-loop merge result: {result[:150]}...")
                return result
        except Exception as exc:
            logger.error(f"[SPN ControlPoint] LLM merge failed: {exc}")
        return "Self-loop processing complete (LLM unavailable)."

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
