# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Versioned role dispatch wire contract, independent of authoring models.

Both the producer and Host validate these invariants. Workflow dictionaries
remain intact so the contract can prove that only declared bindings changed.
"""

import hashlib
import json
from copy import deepcopy
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from host_agent.dispatch_auth import DispatchValidationError

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=1024, pattern=r"\S")]
BindingGroup = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def content_digest(value: dict[str, Any]) -> str:
    """Canonical role-pilot-v2 SHA-256, sorting only the authorization set."""
    value = deepcopy(value)
    if isinstance(value.get("context"), dict) and isinstance(value["context"].get("authorized_instance_ids"), list):
        value["context"]["authorized_instance_ids"] = sorted(value["context"]["authorized_instance_ids"])
    wire = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(wire.encode("utf-8")).hexdigest()


# Deployment admission (REQ74 P4). The dispatch signature key authenticates a
# message; this gate authorizes the capability itself and is disabled by
# default. The technical-pilot mode is admitted only on explicitly declared
# non-production environments -- production and unrecognized values stay
# closed. There is no self-declared "business certified" bypass in this release.
PILOT_ENVIRONMENTS = ("technical_pilot", "development", "testing")


def role_execution_admitted(mode: str | None, deployment_environment: str | None) -> tuple[bool, list[str]]:
    """Deployment-policy decision shared verbatim by the center and the Host."""
    resolved_mode = (mode or "").strip().lower() or "disabled"
    environment = (deployment_environment or "").strip().lower() or "production"
    if resolved_mode == "disabled":
        return False, ["MODE_DISABLED"]
    if resolved_mode != "pilot":
        return False, ["MODE_INVALID"]
    if environment not in PILOT_ENVIRONMENTS:
        return False, ["ENVIRONMENT_NOT_PERMITTED"]
    return True, []


def _requirement_scheme_names(requirement) -> set[str] | None:
    """Scheme names a security requirement references; ``None`` when malformed."""
    if not isinstance(requirement, dict):
        return None
    schemes = requirement.get("schemes")
    if not isinstance(schemes, dict) or not schemes:
        return None
    return {str(name) for name in schemes}


def auth_declaration_complete(card: dict[str, Any]) -> bool:
    """Requirements non-empty implies structurally valid, declared references.

    Structure is validated before references: a non-dict requirement or a
    non-map ``schemes`` field is incomplete, never a vacuously empty reference
    set. Executability (credentials or provider state) is a Host dispatch
    concern; the shared contract only rejects incomplete declarations. The
    center-side projection reuses this predicate.
    """
    schemes = card.get("securitySchemes")
    requirements = card.get("securityRequirements")
    if not requirements:
        return True
    if not isinstance(schemes, dict) or not schemes or not isinstance(requirements, list):
        return False
    declared = {str(name) for name in schemes}
    for requirement in requirements:
        names = _requirement_scheme_names(requirement)
        if names is None or not names <= declared:
            return False
    return True


def interface_url_admissible(url) -> bool:
    """One interface URL is clean HTTP(S): host present, no embedded credentials.

    Unparsable URLs (``urlparse`` raises ``ValueError``) are inadmissible
    instead of aborting the caller's whole validation batch.
    """
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return False
    return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None)


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ExecutionScope(WireModel):
    tenant: Identifier
    site: Identifier
    business_object: Identifier

    @model_validator(mode="after")
    def require_concrete_scope(self):
        if any(value == "*" or value != value.strip() for value in self.model_dump().values()):
            raise ValueError("Execution scope must be concrete and normalized")
        return self

    def as_path(self) -> str:
        return f"{self.tenant}/{self.site}/{self.business_object}"


class ExecutionContext(WireModel):
    caller_id: Identifier
    scope: ExecutionScope
    authorized_instance_ids: list[Identifier]


class RoleBinding(WireModel):
    # Workflow identifiers follow PSOP, rather than catalog identifier limits.
    task_id: str
    role_id: Identifier
    role_version: Identifier
    role_skill_id: Identifier
    instance_id: Identifier
    instance_skill_id: Identifier
    execution_skill: Identifier
    binding_group: BindingGroup | None = None
    agent: Identifier
    endpoint: Identifier
    selection_reason: Identifier
    selected_priority: int
    candidates: list[Identifier]
    candidate_priorities: dict[Identifier, int]
    exclusions: dict[Identifier, list[Identifier]]


class FrozenCard(WireModel):
    instance_id: Identifier
    agent_name: Identifier
    endpoint: Identifier
    card: dict[str, Any]
    fingerprint: Digest


class TaskShape(BaseModel):
    """Only the task fields involved in binding; other workflow fields survive."""

    model_config = ConfigDict(extra="allow", strict=True)
    task_id: str
    agent: str
    skill: str
    binding: Literal["instance", "role"]
    role_version: Identifier | None
    binding_group: BindingGroup | None


class StepShape(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    name: str
    type: Literal["AllSuccess", "AnySuccess", "SelfLoop"]
    subtasks: list[TaskShape]


def _require(condition: bool, reason: str, message: str, binding: RoleBinding | None = None) -> None:
    if not condition:
        raise DispatchValidationError(message, reason=reason,
            task_ids=(binding.task_id,) if binding else (),
            instance_id=binding.instance_id if binding else None,
            binding_group=binding.binding_group if binding else None,
            role_ids=(binding.role_id,) if binding else ())


class RoleSnapshot(WireModel):
    schema_version: Literal["role-pilot-v2"] = "role-pilot-v2"
    execution_id: Identifier
    catalog_version: Identifier
    # Content digest of the exact approved catalog release the center used.
    # Carries catalog content changes (same version, edited description) into
    # the snapshot digest and thus into the dispatch signature.
    catalog_fingerprint: Digest
    config_version: Identifier
    policy_version: Identifier
    context: ExecutionContext
    template: dict[str, Any]
    template_fingerprint: Digest
    execution_psop: dict[str, Any]
    bindings: list[RoleBinding] = Field(min_length=1)
    cards: list[FrozenCard] = Field(min_length=1)
    fingerprint: Digest

    @model_validator(mode="after")
    def verify(self):
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        _require(self.fingerprint == content_digest(payload), "SNAPSHOT_DIGEST", "Execution snapshot fingerprint mismatch")
        _require(self.template_fingerprint == content_digest(self.template), "TEMPLATE_DIGEST", "Template fingerprint mismatch")
        _require(self.catalog_version == self.template.get("catalog_version"), "CATALOG_REFERENCE", "Catalog version mismatch")
        _require(bool(self.template.get("id")), "TEMPLATE_ID", "Missing template identity")
        raw_steps = self.template.get("steps")
        _require(isinstance(raw_steps, list), "WORKFLOW_SCHEMA", "Invalid workflow steps")
        steps = [StepShape.model_validate(step) for step in raw_steps]
        tasks = [task for step in steps for task in step.subtasks]
        roles = {task.task_id: task for task in tasks if task.binding == "role"}
        _require(bool(roles), "TASK_COVERAGE", "Execution snapshots require role tasks")
        _require(len({task.task_id for task in tasks}) == len(tasks), "TASK_COVERAGE", "Duplicate task IDs")
        bindings = {binding.task_id: binding for binding in self.bindings}
        _require(len(bindings) == len(self.bindings) and set(bindings) == set(roles),
                 "TASK_COVERAGE", "Task bindings must cover the template exactly once")
        cards = {card.instance_id: card for card in self.cards}
        _require(len(cards) == len(self.cards) and set(cards) == {binding.instance_id for binding in self.bindings},
                 "CARD_COVERAGE", "Cards must cover selected instances exactly once")
        names = {card.agent_name for card in self.cards}
        legacy_names = {task.agent for task in tasks if task.binding == "instance"}
        _require(len(names) == len(cards) and not names.intersection(legacy_names),
                 "AGENT_NAME_COLLISION", "Duplicate selected agent name or legacy task conflict")
        for card in self.cards:
            _require(card.fingerprint == content_digest(card.card), "CARD_DIGEST", "Card fingerprint mismatch")
            _require(card.agent_name == card.card.get("name"), "CARD_IDENTITY", "Card identity mismatch")
            interfaces = card.card.get("supportedInterfaces", [])
            _require(isinstance(interfaces, list) and bool(interfaces)
                     and all(isinstance(interface, dict) for interface in interfaces),
                     "CARD_INTERFACE", "Card must declare at least one interface")
            _require(any(interface.get("protocolBinding") == "HTTP+JSON"
                         and interface.get("url") == card.endpoint for interface in interfaces),
                     "CARD_INTERFACE", "Card endpoint must match a declared HTTP+JSON interface")
            for interface in interfaces:
                _require(interface_url_admissible(interface.get("url")), "CARD_INTERFACE",
                         "Interface URLs must be HTTP(S) without embedded credentials")
            capabilities = card.card.get("capabilities", {})
            _require(isinstance(capabilities, dict), "CARD_SCHEMA", "Invalid card capabilities")
            _require(auth_declaration_complete(card.card), "AUTH_DECLARATION_INCOMPLETE",
                     "Security requirements must reference schemes declared on the card")
        self._verify_execution_copy(steps, bindings, cards)
        return self

    def _verify_execution_copy(self, steps: list[StepShape], bindings: dict[str, RoleBinding],
                               cards: dict[str, FrozenCard]) -> None:
        expected = deepcopy(self.template)
        expected["catalog_version"] = None
        groups: dict[str, tuple[str, str, str]] = {}
        for raw_step, step in zip(expected["steps"], steps, strict=True):
            for raw_task, task in zip(raw_step["subtasks"], step.subtasks, strict=True):
                if task.binding != "role":
                    _require(task.role_version is None and task.binding_group is None,
                             "ROLE_REFERENCE", "Instance tasks cannot carry role fields")
                    continue
                binding = bindings[task.task_id]
                _require(step.type != "SelfLoop", "ROLE_SELF_LOOP", "Role binding is not supported in SelfLoop", binding)
                _require((binding.role_id, binding.role_version, binding.role_skill_id, binding.binding_group) == (
                    task.agent, task.role_version, task.skill, task.binding_group),
                    "ROLE_REFERENCE", "Original role reference mismatch", binding)
                _require(binding.instance_id in self.context.authorized_instance_ids,
                         "NOT_AUTHORIZED", "Selected instance is not authorized", binding)
                if task.binding_group:
                    identity = (task.agent, binding.role_version, binding.instance_id)
                    _require(groups.setdefault(task.binding_group, identity) == identity,
                             "BINDING_GROUP", "Binding group instance mismatch", binding)
                card = cards[binding.instance_id]
                _require((binding.agent, binding.endpoint) == (card.agent_name, card.endpoint),
                         "CARD_IDENTITY", "Binding card identity mismatch", binding)
                skills = card.card.get("skills", [])
                _require(isinstance(skills, list) and all(isinstance(skill, dict) for skill in skills),
                         "CARD_SKILL", "Invalid card skills", binding)
                matching = [skill for skill in skills if skill.get("id") == binding.instance_skill_id]
                _require(len(matching) == 1 and matching[0].get("name") == binding.execution_skill,
                         "CARD_SKILL", "Selected skill mismatch", binding)
                raw_task.update(agent=binding.agent, skill=binding.execution_skill, binding="instance",
                                role_version=None, binding_group=None)
        _require(expected == self.execution_psop, "EXECUTION_COPY", "Execution copy differs from resolved template")

    def binding_metadata(self) -> dict[str, Any]:
        return {"catalog_version": self.catalog_version, "config_version": self.config_version,
                "policy_version": self.policy_version, "scope": self.context.scope.as_path(),
                "bindings": [binding.model_dump(mode="json") for binding in self.bindings]}
