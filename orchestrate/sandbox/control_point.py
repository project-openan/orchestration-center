from __future__ import annotations

from workflow_engine import (
    MessageContent,
    NegotiationReply,
    RouteDecision,
    TaskResult,
)

from orchestrate.sandbox.i18n import translate


class SandboxControlPoint:
    """Generic sandbox policy; it never contains business-specific rules."""

    def __init__(
        self,
        *,
        orch_url: str | None = None,
        ssl_verify: bool = False,
        lang: str = "zh",
    ) -> None:
        del orch_url, ssl_verify
        self.lang = lang

    async def on_task(self, request):
        return MessageContent.text(translate(
            self.lang,
            "stub.task_content",
            step_name=request.step_name,
            instruction=request.instruction,
        ))

    async def on_self_task(self, request):
        result = translate(
            self.lang,
            "sandbox_control_point.self_task_result",
            step_name=request.step_name,
        )
        return TaskResult.succeeded((result,))

    async def on_route(self, request):
        return RouteDecision.allow(translate(
            self.lang,
            "sandbox_control_point.route_allowed",
        ))

    async def on_negotiation(self, request):
        return NegotiationReply.send(MessageContent.text(translate(
            self.lang,
            "stub.negotiation_completed",
        )))
