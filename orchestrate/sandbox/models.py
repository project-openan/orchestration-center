from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orchestrate.validation.sandbox_validator import SandboxCheck, SandboxCheckStatus


class StubScenario(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DELAY = "delay"
    NEGOTIATION = "negotiation"


class StubTemplate(BaseModel):
    """Restricted declarative Stub response override."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(default_factory=lambda: str(uuid4()), max_length=128)
    workflow_id: str | None = Field(None, max_length=128)
    step: str | None = Field(None, max_length=256)
    subtask_index: int | None = None
    agent: str | None = Field(None, max_length=256)
    skill: str | None = Field(None, max_length=256)
    card_name: str | None = Field(None, max_length=256)
    scenario: StubScenario = StubScenario.SUCCESS
    response_text: str | None = Field(None, max_length=20000)
    error_code: str = Field("stub.task_failed", max_length=128)
    delay_ms: int = Field(default=0, ge=0, le=10_000)

    @field_validator("workflow_id", "step", "agent", "skill", "card_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def specificity(self) -> int:
        if self.step and self.subtask_index is not None:
            return 7
        if self.agent and self.skill:
            return 6
        if self.agent:
            return 5
        if self.card_name:
            return 4
        return 3

    def matches(
        self,
        *,
        workflow_id: str,
        step: str,
        subtask_index: int,
        agent: str,
        skill: str,
        card_name: str,
    ) -> bool:
        checks = (
            (self.workflow_id, workflow_id),
            (self.step, step),
            (self.agent, agent),
            (self.skill, skill),
            (self.card_name, card_name),
        )
        for expected, actual in checks:
            if expected is not None and expected != actual:
                return False
        return not (
            self.subtask_index is not None and self.subtask_index != subtask_index
        )


class ContextTrace(BaseModel):
    step: str
    subtask_index: int
    agent: str
    skill: str
    upstream_steps: list[str] = Field(default_factory=list)
    upstream_result_count: int = 0


class StubInteraction(BaseModel):
    step: str
    subtask_index: int
    agent: str
    skill: str
    scenario: StubScenario
    template_id: str
    task_state: str
    response_text: str
    error_code: str | None = None
    negotiation_rounds: int = 0


class SandboxRunReport(BaseModel):
    verification_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    workflow_name: str
    mode: str = "sandbox"
    scenario: StubScenario
    verdict: SandboxCheckStatus
    static_checks: list[SandboxCheck] = Field(default_factory=list)
    execution_path: list[str] = Field(default_factory=list)
    context_trace: list[ContextTrace] = Field(default_factory=list)
    stub_interactions: list[StubInteraction] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    error: str | None = None


_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
ALLOWED_TEMPLATE_VARIABLES = {
    "workflow_id",
    "workflow_name",
    "intent",
    "step_name",
    "task_description",
    "skill",
    "agent",
}


def render_template(
    template: str,
    values: Mapping[str, Any],
    *,
    workflow_id: str = "",
    workflow_name: str = "",
    intent: str = "",
    step_name: str = "",
    task_description: str = "",
    skill: str = "",
    agent: str = "",
) -> str:
    """Replace whitelisted variables only; never evaluate expressions."""
    allowed = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "intent": intent,
        "step_name": step_name,
        "task_description": task_description,
        "skill": skill,
        "agent": agent,
    }
    for value in allowed.values():
        if value is not None and len(str(value)) > 20_000:
            raise ValueError("Template value exceeds size limit")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in allowed:
            raise ValueError(f"Template variable is not allowed: {name}")
        return str(allowed.get(name, values.get(name, "")))

    return _VARIABLE_PATTERN.sub(replace, template)
