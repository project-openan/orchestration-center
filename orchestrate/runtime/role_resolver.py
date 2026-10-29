# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Pure, deterministic selection for technical pilots; no dispatch or I/O.

This returns a proposed execution copy. Host verification and full-card freezing
must be connected before these results may be dispatched in production.

``evaluate_selection_units`` is the single rule core shared by formal
resolution (all-or-nothing) and execution preview (collects every unit's
diagnostics), so the two paths cannot drift apart.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from orchestrate.core.model.instance_binding import (
    InstanceRegistry, ObservedInstance, ResolutionContext, ResolutionPolicy,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog


class ResolutionError(ValueError):
    def __init__(self, code, message, *, task_ids=(), binding_group=None, exclusions=None, candidates=()):
        self.code = code
        self.task_ids = list(task_ids)
        self.binding_group = binding_group
        self.exclusions = deepcopy(exclusions or {})
        self.candidates = list(candidates)
        super().__init__(f"{code}: {message}")


@dataclass
class ResolutionResult:
    execution_psop: PSOP
    bindings: list[dict]
    catalog_version: str
    config_version: str
    policy_version: str
    context: ResolutionContext


@dataclass
class SelectionUnit:
    """One candidate-selection unit: an independent task or a binding group."""

    kind: str  # "task" | "group"
    key: str
    members: list = field(default_factory=list)


@dataclass
class UnitEvaluation:
    """Per-unit filter and selection outcome; ``error`` replaces raising."""

    kind: str
    key: str
    members: list = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    binding_group: Optional[str] = None
    candidates: list = field(default_factory=list)
    exclusions: dict = field(default_factory=dict)
    mappings: dict = field(default_factory=dict)
    chosen: Optional[ObservedInstance] = None
    reason: Optional[str] = None
    error: Optional[ResolutionError] = None

    @property
    def detail(self) -> dict:
        return dict(task_ids=list(self.task_ids), binding_group=self.binding_group,
                    exclusions=deepcopy(self.exclusions),
                    candidates=[i.instance_id for i in self.candidates])


def selection_units(psop: PSOP) -> list[SelectionUnit]:
    """Group role tasks into selection units in first-appearance order."""
    units: dict[tuple, SelectionUnit] = {}
    for step in psop.steps:
        for task in step.subtasks:
            if task.binding != "role":
                continue
            # Namespace group IDs independently of task IDs.
            key = ("group", task.binding_group) if task.binding_group else ("task", task.task_id)
            units.setdefault(key, SelectionUnit(kind=key[0], key=key[1])).members.append(task)
    return list(units.values())


def _hard_filters(unit: SelectionUnit, registry: InstanceRegistry,
                  observed: dict, context: ResolutionContext) -> UnitEvaluation:
    """Shared candidate filtering; the only place eligibility is decided."""
    evaluation = UnitEvaluation(kind=unit.kind, key=unit.key, members=list(unit.members),
                                task_ids=[t.task_id for t in unit.members],
                                binding_group=unit.key if unit.kind == "group" else None)
    for instance in sorted(registry.instances, key=lambda i: i.instance_id):
        reasons = []
        card = observed.get(instance.instance_id)
        if not instance.enabled or instance.technical_status != "passed":
            reasons.append("TECHNICAL_ADMISSION_REQUIRED")
        if instance.instance_id not in context.authorized_instance_ids:
            reasons.append("NOT_AUTHORIZED")
        if not any(scope.covers(context.scope) for scope in instance.scopes):
            reasons.append("OUT_OF_SCOPE")
        if card is None:
            reasons.append("INSTANCE_NOT_VISIBLE")
        elif (card.agent_name, card.endpoint) != (instance.agent_name, instance.endpoint):
            reasons.append("INSTANCE_SNAPSHOT_MISMATCH")
        if card is not None and not card.prerequisites_passed:
            reasons.append("PREREQUISITES_NOT_MET")
        index = {(s.role_id, s.role_version, s.skill_id): s for s in instance.skills}
        for task in unit.members:
            mapping = index.get((task.agent, task.role_version, task.skill))
            if mapping is None:
                reasons.append("MISSING_ROLE_SKILL")
            elif card is not None and card.skills.get(mapping.instance_skill_id) != mapping.execution_skill:
                reasons.append("INSTANCE_SKILL_MISMATCH")
        if reasons:
            evaluation.exclusions[instance.instance_id] = sorted(set(reasons))
        else:
            evaluation.candidates.append(instance)
            evaluation.mappings[instance.instance_id] = index
    return evaluation


def evaluate_unit(unit: SelectionUnit, registry: InstanceRegistry, observed: dict,
                  context: ResolutionContext, policy: ResolutionPolicy) -> UnitEvaluation:
    """Filter candidates then apply overrides, priority and tie-break.

    Never raises: a failed selection is returned as ``evaluation.error`` so
    preview can collect every unit's diagnostics and formal resolution can
    raise it unchanged.
    """
    evaluation = _hard_filters(unit, registry, observed, context)
    overrides = {policy.task_overrides[t.task_id] for t in unit.members if t.task_id in policy.task_overrides}
    if unit.kind == "group" and unit.key in policy.group_overrides:
        overrides.add(policy.group_overrides[unit.key])
    if len(overrides) > 1:
        evaluation.error = ResolutionError("INVALID_OVERRIDE", "Conflicting group overrides", **evaluation.detail)
        return evaluation
    if overrides:
        chosen = next((i for i in evaluation.candidates if i.instance_id in overrides), None)
        if chosen is None:
            evaluation.error = ResolutionError("INVALID_OVERRIDE", "Override fails hard constraints", **evaluation.detail)
            return evaluation
        evaluation.chosen = chosen
        evaluation.reason = "explicit_override"
        return evaluation
    if not evaluation.candidates:
        code = "BINDING_GROUP_UNSATISFIED" if unit.kind == "group" else "NO_ELIGIBLE_INSTANCE"
        evaluation.error = ResolutionError(
            code, "No instance satisfies all required skills and scope", **evaluation.detail)
        return evaluation
    best = max(i.priority for i in evaluation.candidates)
    top = [i for i in evaluation.candidates if i.priority == best]
    if len(top) > 1 and policy.tie_break == "error":
        evaluation.error = ResolutionError("AMBIGUOUS_BINDING", "Equal-priority candidates", **evaluation.detail)
        return evaluation
    evaluation.chosen = min(top, key=lambda i: i.instance_id)
    evaluation.reason = "instance_id_tie_break" if len(top) > 1 else "highest_priority"
    return evaluation


def evaluate_selection_units(psop: PSOP, registry: InstanceRegistry, observations: list[ObservedInstance],
                             context: ResolutionContext, policy: ResolutionPolicy):
    """Evaluate every selection unit without raising.

    Returns ``(evaluations, error)``. ``error`` carries a global pre-unit
    failure (overrides referencing unknown role tasks or groups); unit-level
    failures stay on their ``UnitEvaluation.error``.
    """
    tasks = [t for step in psop.steps for t in step.subtasks if t.binding == "role"]
    ids = {t.task_id for t in tasks}
    groups = {t.binding_group for t in tasks if t.binding_group}
    if set(policy.task_overrides) - ids or set(policy.group_overrides) - groups:
        return [], ResolutionError(
            "INVALID_OVERRIDE", "Override refers to unknown role task or group",
            task_ids=[t.task_id for t in tasks])
    observed = {o.instance_id: o for o in observations}
    return ([evaluate_unit(unit, registry, observed, context, policy) for unit in selection_units(psop)],
            None)


def resolve_role_bindings(
    psop: PSOP,
    catalog: RoleCatalog,
    registry: InstanceRegistry,
    observations: list[ObservedInstance],
    context: ResolutionContext,
    policy: ResolutionPolicy,
) -> ResolutionResult:
    # Revalidate to catch callers mutating Pydantic objects after construction.
    psop = PSOP.model_validate(psop.model_dump())
    catalog = RoleCatalog.model_validate(catalog.model_dump())
    registry = InstanceRegistry.model_validate(registry.model_dump())
    context = ResolutionContext.model_validate(context.model_dump())
    policy = ResolutionPolicy.model_validate(policy.model_dump())
    observations = [ObservedInstance.model_validate(o.model_dump()) for o in observations]
    tasks = [t for step in psop.steps for t in step.subtasks if t.binding == "role"]
    try:
        catalog.validate_workflow(psop)
    except ValueError as exc:
        code = str(exc).split(":")[0]
        raise ResolutionError(code, str(exc), task_ids=[t.task_id for t in tasks]) from exc

    observed = {o.instance_id: o for o in observations}
    if len(observed) != len(observations):
        raise ResolutionError("INSTANCE_SNAPSHOT_MISMATCH", "Duplicate observed instance ID")

    evaluations, global_error = evaluate_selection_units(psop, registry, observations, context, policy)
    if global_error is not None:
        raise global_error
    for evaluation in evaluations:
        if evaluation.error is not None:
            raise evaluation.error

    selected = {}
    records = []
    for evaluation in evaluations:
        chosen = evaluation.chosen
        for task in evaluation.members:
            mapping = evaluation.mappings[chosen.instance_id][(task.agent, task.role_version, task.skill)]
            selected[task.task_id] = (chosen, mapping)
            records.append({
                "task_id": task.task_id, "binding_group": task.binding_group,
                "role_id": task.agent, "role_version": task.role_version,
                "role_skill_id": task.skill, "instance_id": chosen.instance_id,
                "agent": chosen.agent_name, "endpoint": chosen.endpoint,
                "instance_skill_id": mapping.instance_skill_id,
                "execution_skill": mapping.execution_skill,
                "selection_reason": evaluation.reason,
                "selected_priority": chosen.priority,
                "candidates": [i.instance_id for i in evaluation.candidates],
                "candidate_priorities": {i.instance_id: i.priority for i in evaluation.candidates},
                "exclusions": deepcopy(evaluation.exclusions),
            })

    names = {}
    legacy_names = {t.agent for s in psop.steps for t in s.subtasks if t.binding == "instance"}
    for instance, _ in selected.values():
        previous = names.setdefault(instance.agent_name, instance.instance_id)
        if previous != instance.instance_id or instance.agent_name in legacy_names:
            raise ResolutionError(
                "INSTANCE_SNAPSHOT_MISMATCH",
                "Selected name is ambiguous with another selected or legacy instance",
            )
    data = psop.model_dump(mode="json")
    data["catalog_version"] = None
    for step in data["steps"]:
        for task in step["subtasks"]:
            if task["task_id"] not in selected:
                continue
            instance, mapping = selected[task["task_id"]]
            task.update(agent=instance.agent_name, skill=mapping.execution_skill,
                        binding="instance", role_version=None, binding_group=None)
    return ResolutionResult(
        execution_psop=PSOP.model_validate(data), bindings=records,
        catalog_version=catalog.catalog_version, config_version=registry.config_version,
        policy_version=policy.policy_version, context=context.model_copy(deep=True),
    )
