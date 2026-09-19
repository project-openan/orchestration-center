from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from loguru import logger
from workflow_engine import (
    MessageContent,
    NegotiationRequest,
    ReceivedMessage,
    SendMessageResult,
)
from workflow_engine.control.control_points import EventType
from workflow_engine.core.models import TaskRequest

from orchestrate.sandbox.models import (
    ContextTrace,
    StubInteraction,
    StubScenario,
    StubTemplate,
    render_template,
)
from orchestrate.sandbox.i18n import translate

TASK_T_URI = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"
NEGOTIATION_T_URI = (
    "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Negotiation-T/v1"
)
NEGOTIATION_CONTEXT_KEY = "negotiationContext"
TEMPLATE_URI_KEY = "templateUri"
TASK_TEMPLATE_URI = "Task-T/sandbox/stub/v1"
NEGOTIATION_TEMPLATE_URI = "Negotiation-T/sandbox/information/propose/v1"
TERMINAL_ROUTES = {"end", "retry", "endNode"}


class StubAgentRuntime:
    """WorkflowEngineClient-compatible transport backed by local stubs."""

    callback_timeout_seconds = 600

    def __init__(
        self,
        agent_cards: list[Any] | None = None,
        *,
        scenario: StubScenario = StubScenario.SUCCESS,
        templates: list[StubTemplate] | None = None,
        workflow_id: str = "",
        workflow_name: str = "",
        intent: str = "",
        lang: str = "zh",
    ) -> None:
        self._card_map = {
            getattr(card, "name", ""): card for card in (agent_cards or [])
        }
        self.scenario = scenario
        self.templates = list(templates or [])
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.intent = intent
        self.lang = str(lang).lower()
        self.context_trace: list[ContextTrace] = []
        self.stub_interactions: list[StubInteraction] = []
        self._request_counts: dict[tuple[str, str, str], int] = {}
        self._event_callback: Callable[[str, dict], None] | None = None
        self._closed = False

    @property
    def agent_names(self) -> list[str]:
        return list(self._card_map)

    def get_card(self, agent_name: str):
        return self._card_map.get(agent_name)

    def update_agent_cards(self, agent_cards: list[Any]) -> None:
        self._card_map = {
            getattr(card, "name", ""): card for card in agent_cards
        }

    def begin_execution(
        self,
        execution_id: str,
        control_point,
        event_callback,
    ) -> None:
        del execution_id, control_point
        self._event_callback = event_callback
        self._request_counts = {}

    def end_execution(self, execution_id: str) -> None:
        del execution_id
        self._event_callback = None

    async def close(self) -> None:
        self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def send_message(self, agent_name: str, content: MessageContent) -> SendMessageResult:
        del agent_name, content
        text = "Stub response"
        return self._result(text)

    async def dispatch(self, request: TaskRequest, content: MessageContent, callbacks=None) -> SendMessageResult:
        if self._closed:
            raise RuntimeError("StubAgentRuntime is closed")

        dispatch_key = (
            request.execution_id,
            request.step_name,
            request.agent_name,
        )
        subtask_index = self._request_counts.get(dispatch_key, 0)
        self._request_counts[dispatch_key] = subtask_index + 1
        context = ContextTrace(
            step=request.step_name,
            subtask_index=subtask_index,
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
        )
        self.context_trace.append(context)
        template = self._select_template(request, subtask_index)
        self._emit(EventType.AGENT_REQUEST, {
            "agent": request.agent_name,
            "content": content,
        })

        if template.delay_ms:
            await asyncio.sleep(template.delay_ms / 1000)

        rendered = self._response_text(template, request)
        if template.scenario == StubScenario.ERROR:
            self._interaction(
                request,
                template,
                "TASK_STATE_FAILED",
                rendered,
                template.error_code,
                subtask_index=subtask_index,
            )
            self._emit(EventType.AGENT_RESPONSE, {
                "agent": request.agent_name,
                "response": rendered,
                "received_messages": (),
            })
            return SendMessageResult(
                text=rendered,
                metadata={TASK_T_URI: rendered, TEMPLATE_URI_KEY: TASK_TEMPLATE_URI},
                task_state="TASK_STATE_FAILED",
                failure_code=template.error_code,
                failure_message=rendered,
                received_messages=(ReceivedMessage(message=MessageContent.text(rendered)),),
            )

        if template.scenario == StubScenario.NEGOTIATION:
            return await self._negotiation(request, content, callbacks, template)

        self._interaction(
            request,
            template,
            "TASK_STATE_COMPLETED",
            rendered,
            subtask_index=subtask_index,
        )
        self._emit(EventType.AGENT_RESPONSE, {
            "agent": request.agent_name,
            "response": rendered,
            "received_messages": (),
        })
        return self._result(rendered)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_callback is not None:
            on_event = getattr(self._event_callback, "on_event", self._event_callback)
            on_event(event_type, data)

    def _select_template(self, request: TaskRequest, subtask_index: int) -> StubTemplate:
        card_name = request.agent_name
        candidates = [
            template for template in self.templates
            if template.matches(
                workflow_id=self.workflow_id,
                step=request.step_name,
                subtask_index=subtask_index,
                agent=request.agent_name,
                skill=request.skill,
                card_name=card_name,
            )
        ]
        if not candidates:
            return StubTemplate(
                template_id="generated-card-default",
                scenario=self.scenario,
                response_text=self._default_response(request),
                delay_ms=500 if self.scenario == StubScenario.DELAY else 0,
            )
        return max(candidates, key=lambda item: item.specificity)

    def _default_response(self, request: TaskRequest) -> str:
        card = self._card_map.get(request.agent_name)
        skill_description = ""
        if card is not None:
            for skill in getattr(card, "skills", ()) or ():
                if getattr(skill, "id", "") == request.skill:
                    skill_description = getattr(skill, "description", "") or skill_description
                    break
        description = skill_description or getattr(card, "description", "") or "declared AgentCard capability"
        return translate(
            self.lang,
            "stub.default_response",
            agent=request.agent_name,
            skill=request.skill,
            scenario=self.scenario.value,
            description=description,
        )

    def _response_text(self, template: StubTemplate, request: TaskRequest) -> str:
        text = template.response_text or self._default_response(request)
        return render_template(
            text,
            {},
            workflow_id=self.workflow_id,
            workflow_name=self.workflow_name,
            intent=self.intent,
            step_name=request.step_name,
            task_description=request.instruction,
            skill=request.skill,
            agent=request.agent_name,
        )

    def _result(self, text: str) -> SendMessageResult:
        received = ReceivedMessage(
            message=MessageContent.text(text),
            task_metadata={TASK_T_URI: text, TEMPLATE_URI_KEY: TASK_TEMPLATE_URI},
        )
        return SendMessageResult(
            text=text,
            metadata={TASK_T_URI: text, TEMPLATE_URI_KEY: TASK_TEMPLATE_URI},
            task_state="TASK_STATE_COMPLETED",
            received_messages=(received,),
        )

    def _interaction(
        self,
        request: TaskRequest,
        template: StubTemplate,
        task_state: str,
        text: str,
        error_code: str | None = None,
        negotiation_rounds: int = 0,
        subtask_index: int = 0,
    ) -> StubInteraction:
        interaction = StubInteraction(
            step=request.step_name,
            subtask_index=subtask_index,
            agent=request.agent_name,
            skill=request.skill,
            scenario=template.scenario,
            template_id=template.template_id,
            task_state=task_state,
            response_text=text,
            error_code=error_code,
            negotiation_rounds=negotiation_rounds,
        )
        self.stub_interactions.append(interaction)
        return interaction

    async def _negotiation(
        self,
        request: TaskRequest,
        content: MessageContent,
        callbacks,
        template: StubTemplate,
    ) -> SendMessageResult:
        from a2a_t.core import NegotiationContext, NegotiationPerformative
        from workflow_engine import NegotiationSend, NegotiationStop

        if callbacks is None:
            raise RuntimeError("on_negotiation callback is required")
        context_id = str(uuid4())
        context = NegotiationContext(
            context_id,
            1,
            3,
            NegotiationPerformative.PROPOSE,
        )
        proposal = translate(self.lang, "stub.negotiation_proposal")
        metadata = {
            NEGOTIATION_T_URI: proposal,
            TEMPLATE_URI_KEY: NEGOTIATION_TEMPLATE_URI,
            NEGOTIATION_CONTEXT_KEY: {
                "id": context.id,
                "round": context.round,
                "maxRounds": context.max_rounds,
                "performative": context.performative.value,
            },
        }
        received = ReceivedMessage(task_metadata=metadata)
        request_model = NegotiationRequest(
            task=request,
            original_submission=content,
            received=received,
            previous_exchanges=(),
            remaining_wait_seconds=30,
        )
        self._emit(EventType.NEGOTIATION_REQUEST, {
            "agent": request.agent_name,
            "request": request_model,
            "exchange": 1,
        })
        reply = await callbacks.on_negotiation(request_model)
        if isinstance(reply, NegotiationStop):
            logger.info(f"[StubAgentRuntime] Negotiation stopped: {reply.code}")
            self._interaction(
                request,
                template,
                "TASK_STATE_FAILED",
            reply.reason,
            reply.code,
            negotiation_rounds=1,
            subtask_index=self._request_counts.get(
                (request.execution_id, request.step_name, request.agent_name), 1
            ) - 1,
        )
            self._emit(EventType.AGENT_RESPONSE, {
                "agent": request.agent_name,
                "response": reply.reason,
                "received_messages": (),
            })
            return SendMessageResult(
                text=reply.reason,
                task_state="TASK_STATE_FAILED",
                failure_code=reply.code,
                failure_message=reply.reason,
            )
        if not isinstance(reply, NegotiationSend):
            raise TypeError("on_negotiation must return NegotiationSend or NegotiationStop")

        self._emit(EventType.NEGOTIATION_RESOLVED, {
            "agent": request.agent_name,
            "exchange": 1,
            "reply": reply,
        })
        text = template.response_text or translate(
            self.lang,
            "stub.negotiation_completed",
        )
        self._interaction(
            request,
            template,
            "TASK_STATE_COMPLETED",
            text,
            negotiation_rounds=1,
            subtask_index=self._request_counts.get(
                (request.execution_id, request.step_name, request.agent_name), 1
            ) - 1,
        )
        self._emit(EventType.AGENT_RESPONSE, {
            "agent": request.agent_name,
            "response": text,
            "received_messages": (),
        })
        return SendMessageResult(
            text=text,
            metadata={TASK_T_URI: text, TEMPLATE_URI_KEY: TASK_TEMPLATE_URI},
            task_state="TASK_STATE_COMPLETED",
            received_messages=(ReceivedMessage(message=MessageContent.text(text)),),
        )
