from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from loguru import logger
from workflow_engine import execute_psop, MessageContent, NegotiationReply

from orchestrate.core.model.psop import PSOP
from orchestrate.sandbox.models import (
    ContextTrace,
    SandboxRunReport,
    StubScenario,
    StubTemplate,
)
from orchestrate.sandbox.i18n import translate
from orchestrate.sandbox.stub_runtime import StubAgentRuntime
from orchestrate.validation.sandbox_validator import (
    SandboxCheckStatus,
    validate_sandbox_static,
)


class _ContextRecordingControlPoint:
    """Record local SelfLoop context that does not pass through Stub transport."""

    def __init__(self, delegate, context_trace: list[ContextTrace]) -> None:
        self._delegate = delegate
        self._context_trace = context_trace

    async def on_task(self, request):
        return await self._delegate.on_task(request)

    async def on_self_task(self, request):
        self._context_trace.append(ContextTrace(
            step=request.step_name,
            subtask_index=0,
            agent=request.agent_name,
            skill=request.skill,
            upstream_steps=[
                upstream.step_name
                for upstream in request.workflow_input.upstream_results
            ],
            upstream_result_count=sum(
                len(upstream.task_results)
                for upstream in request.workflow_input.upstream_results
            ),
        ))
        return await self._delegate.on_self_task(request)

    async def on_route(self, request):
        return await self._delegate.on_route(request)

    async def on_negotiation(self, request):
        return await self._delegate.on_negotiation(request)


class _SandboxTaskContentControlPoint:
    """Replace business content generation while preserving local flow policy."""

    def __init__(self, delegate, lang: str) -> None:
        self._delegate = delegate
        self._lang = lang

    async def on_task(self, request):
        return MessageContent.text(translate(
            self._lang,
            "stub.task_content",
            step_name=request.step_name,
            instruction=request.instruction,
        ))

    async def on_self_task(self, request):
        return await self._delegate.on_self_task(request)

    async def on_route(self, request):
        return await self._delegate.on_route(request)

    async def on_negotiation(self, request):
        return NegotiationReply.send(MessageContent.text(translate(
            self._lang,
            "stub.negotiation_completed",
        )))


def _scenario(value: StubScenario | str) -> StubScenario:
    return value if isinstance(value, StubScenario) else StubScenario(value)


def _verdict(events: list[dict[str, Any]], static_verdict: SandboxCheckStatus) -> SandboxCheckStatus:
    if any(event.get("type") == "error" for event in events):
        return SandboxCheckStatus.FAIL
    if static_verdict == SandboxCheckStatus.WARNING:
        return SandboxCheckStatus.WARNING
    return SandboxCheckStatus.PASS


def _risks_and_suggestions(
    events: list[dict[str, Any]],
    static_checks: list[Any],
    scenario: StubScenario,
    lang: str = "zh",
) -> tuple[list[str], list[str]]:
    risks: list[str] = []
    suggestions: list[str] = []
    for check in static_checks:
        if check.status == SandboxCheckStatus.WARNING or check.status == SandboxCheckStatus.FAIL:
            risks.append(f"{check.check_id}: {check.detail}")
            suggestions.extend(check.suggestions)
    if scenario == StubScenario.ERROR:
        risks.append(translate(lang, "report.risk_intentional_error"))
    failed_task = next(
        (
            event for event in events
            if event.get("type") == "task_response"
            and event.get("data", {}).get("status") == "failed"
            and (event.get("data", {}).get("error") or event.get("data", {}).get("error_code"))
        ),
        None,
    )
    if failed_task:
        data = failed_task.get("data", {})
        risks.append(translate(
            lang,
            "report.risk_workflow_error",
            step=data.get("step", "-"),
            error=data.get("error") or data.get("error_code") or "-",
        ))
    if any(event.get("type") == "error" for event in events):
        suggestions.append(translate(lang, "report.suggestion_inspect_error"))
    suggestions.append(translate(lang, "report.suggestion_success_scope"))
    return risks, list(dict.fromkeys(suggestions))


async def run_sandbox(
    psop: PSOP,
    agent_cards: Iterable[Any],
    control_point,
    *,
    verification_id: str | None = None,
    scenario: StubScenario | str = StubScenario.SUCCESS,
    templates: list[StubTemplate] | None = None,
    runtime_intent: str = "",
    lang: str = "zh",
    event_sink=None,
) -> SandboxRunReport:
    """Run static validation and Stub execution through the real workflow runner."""
    scenario_value = _scenario(scenario)
    agent_cards = list(agent_cards)
    static_report = validate_sandbox_static(psop, agent_cards, lang)

    if static_report.verdict == SandboxCheckStatus.FAIL:
        return SandboxRunReport(
            verification_id=verification_id or str(uuid4()),
            workflow_id=psop.id,
            workflow_name=psop.name,
            scenario=scenario_value,
            verdict=SandboxCheckStatus.FAIL,
            static_checks=static_report.checks,
            execution_path=[],
            context_trace=[],
            stub_interactions=[],
            risks=[translate(lang, "report.risk_static_failed")],
            suggestions=[translate(lang, "report.suggestion_fix_static")],
        )

    stub_runtime = StubAgentRuntime(
        agent_cards,
        scenario=scenario_value,
        lang=lang,
        templates=templates,
        workflow_id=psop.id,
        workflow_name=psop.name,
        intent=runtime_intent,
    )
    context_trace = list(stub_runtime.context_trace)
    sandbox_control_point = _SandboxTaskContentControlPoint(
        control_point,
        lang,
    )
    recording_control_point = _ContextRecordingControlPoint(
        sandbox_control_point,
        context_trace,
    )
    events: list[dict[str, Any]] = []
    error: str | None = None
    try:
        async for event in execute_psop(
            psop=psop.model_dump(mode="json"),
            agent_cards=agent_cards,
            control_point=recording_control_point,
            engine_client=stub_runtime,
            runtime_intent=runtime_intent,
            lang=lang,
        ):
            events.append(event)
            if event_sink is not None:
                try:
                    event_sink(event)
                except Exception as exc:
                    logger.warning(f"[Sandbox] Event sink failed: {exc}")
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        events.append({"type": "error", "data": {"error": error}})
    finally:
        await stub_runtime.close()

    verdict = _verdict(events, static_report.verdict)
    risks, suggestions = _risks_and_suggestions(events, static_report.checks, scenario_value, lang)
    if error:
        suggestions.append(translate(lang, "report.suggestion_runner_exception"))

    return SandboxRunReport(
        verification_id=verification_id or str(uuid4()),
        workflow_id=psop.id,
        workflow_name=psop.name,
        scenario=scenario_value,
        verdict=verdict,
        static_checks=static_report.checks,
        execution_path=[
            event["data"]["step"]
            for event in events
            if event.get("type") == "step_start" and event.get("data", {}).get("step")
        ],
        context_trace=context_trace,
        stub_interactions=list(stub_runtime.stub_interactions),
        risks=risks,
        suggestions=suggestions,
        error=error,
    )
