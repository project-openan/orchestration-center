# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Execution preview for role workflows: read-only, no dispatch side effects.

The preview reuses the formal resolver's rules end to end (candidate
eligibility, authorization, scope, skills, priority, overrides) so the two
paths cannot drift. It never creates a business transport, signs in to an
agent, calls an LLM, executes a task, writes a success execution record or
freezes an official execution_id.

Display safety: only instances the caller is authorized to use are named.
Excluded instances outside the authorization ceiling are collapsed into a
single aggregate ``NOT_AUTHORIZED`` entry; names, endpoints and capability
details never appear for them.
"""

import re
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic import ValidationError

from orchestrate.core.model.psop import PSOP
from orchestrate.persistence.errors import RoleReferenceError
from orchestrate.runtime.instance_projection import (
    ResolutionError, ResolutionRequest, assemble_resolution_inputs,
    freeze_resolution_snapshot,
)
from orchestrate.runtime.role_admission import role_execution_admission
from orchestrate.runtime.role_resolver import evaluate_selection_units, resolve_role_bindings

_CODE_PREFIX = re.compile(r"^[A-Z][A-Z0-9_]*$")


class RolePreviewIssue(BaseModel):
    code: str
    message: str
    task_ids: list[str] = Field(default_factory=list)
    binding_group: str | None = None


class RolePreviewSkill(BaseModel):
    task_id: str
    role_id: str
    role_version: str | None
    skill_id: str


class RolePreviewCandidate(BaseModel):
    instance_id: str
    agent_name: str
    priority: int


class RolePreviewExclusion(BaseModel):
    instance_id: str | None = None  # None: aggregate over hidden (unauthorized) instances
    reasons: list[str] = Field(default_factory=list)


class RolePreviewSelection(BaseModel):
    instance_id: str
    agent_name: str
    priority: int
    selection_reason: str


class RolePreviewUnit(BaseModel):
    unit_id: str  # "task:<task_id>" | "group:<binding_group>"
    binding_group: str | None
    task_ids: list[str]
    required_skills: list[RolePreviewSkill]
    current_selection: RolePreviewSelection | None
    candidates: list[RolePreviewCandidate]
    exclusions: list[RolePreviewExclusion]


class RolePreviewAdmission(BaseModel):
    """Deployment admission state: technical candidates do not imply execution admission."""

    allowed: bool
    reasons: list[str] = Field(default_factory=list)


class RolePreviewResponse(BaseModel):
    psop_id: str
    psop_name: str
    template_fingerprint: str | None
    catalog_version: str | None
    config_version: str | None
    policy_version: str | None
    execution_scope: str | None
    caller_id: str | None
    units: list[RolePreviewUnit]
    issues: list[RolePreviewIssue]
    can_execute: bool
    resolution_fingerprint: str | None = None
    execution_admission: RolePreviewAdmission


def _issue(error, code: str | None = None) -> RolePreviewIssue:
    message = str(error)
    resolved_code = code or getattr(error, "code", None)
    if not resolved_code:
        # RoleReferenceError and plain ValueErrors carry an ALL_CAPS message
        # prefix; anything else must not leak as a code (same rule as SSE).
        prefix = message.split(":", 1)[0]
        resolved_code = prefix if _CODE_PREFIX.match(prefix) else "RESOLUTION_FAILED"
    return RolePreviewIssue(
        code=resolved_code,
        message=message,
        task_ids=list(getattr(error, "task_ids", ()) or ()),
        binding_group=getattr(error, "binding_group", None),
    )


def _preview_unit(evaluation, context) -> RolePreviewUnit:
    authorized = context.authorized_instance_ids
    candidates = [
        RolePreviewCandidate(instance_id=i.instance_id, agent_name=i.agent_name, priority=i.priority)
        for i in evaluation.candidates
    ]
    exclusions = []
    hidden = False
    for instance_id, reasons in evaluation.exclusions.items():
        if instance_id in authorized:
            exclusions.append(RolePreviewExclusion(instance_id=instance_id, reasons=reasons))
        else:
            hidden = True
    if hidden:
        # A summarized reason only: unauthorized instances stay unidentifiable.
        exclusions.append(RolePreviewExclusion(instance_id=None, reasons=["NOT_AUTHORIZED"]))
    selection = None
    if evaluation.chosen is not None:
        selection = RolePreviewSelection(
            instance_id=evaluation.chosen.instance_id,
            agent_name=evaluation.chosen.agent_name,
            priority=evaluation.chosen.priority,
            selection_reason=evaluation.reason or "",
        )
    return RolePreviewUnit(
        unit_id=f"{'group' if evaluation.kind == 'group' else 'task'}:{evaluation.key}",
        binding_group=evaluation.binding_group,
        task_ids=list(evaluation.task_ids),
        required_skills=[
            RolePreviewSkill(task_id=t.task_id, role_id=t.agent, role_version=t.role_version, skill_id=t.skill)
            for t in evaluation.members
        ],
        current_selection=selection,
        candidates=candidates,
        exclusions=exclusions,
    )


def _response(psop: PSOP, *, template_fingerprint: str | None, catalog_version=None, config_version=None,
              policy_version=None, scope=None, caller_id=None, units=(), issues=(),
              can_execute=False, fingerprint=None, admission=None) -> RolePreviewResponse:
    from orchestrate.runtime.role_admission import role_execution_admission

    if admission is None:
        allowed, reasons = role_execution_admission()
        admission = RolePreviewAdmission(allowed=allowed, reasons=reasons)
    return RolePreviewResponse(
        psop_id=psop.id, psop_name=psop.name,
        template_fingerprint=template_fingerprint,
        catalog_version=catalog_version, config_version=config_version, policy_version=policy_version,
        execution_scope=scope, caller_id=caller_id,
        units=list(units), issues=list(issues), can_execute=can_execute,
        resolution_fingerprint=fingerprint, execution_admission=admission,
    )


def build_role_preview(psop: PSOP, request: ResolutionRequest | None, agent_cards) -> RolePreviewResponse:
    """Assemble the preview response for one saved role workflow template.

    Domain failures (catalog unavailable, invalid scope, no eligible
    candidates, ambiguity, invalid overrides, card drift) become structured
    issues with ``can_execute=false``; malformed requests raise
    ``ResolutionError`` for the HTTP layer to map.
    """
    from orchestrate.core.model.role_execution_snapshot import content_digest, resolution_fingerprint

    template_fingerprint = content_digest(psop.model_dump(mode="json"))
    allowed, admission_reasons = role_execution_admission()
    admission = RolePreviewAdmission(allowed=allowed, reasons=admission_reasons)

    try:
        inputs = assemble_resolution_inputs(psop, request, agent_cards)
    except ValidationError as error:
        raise ResolutionError("RESOLUTION_INPUT_INVALID", f"invalid resolution inputs: {error}") from error
    except RoleReferenceError as error:
        return _response(psop, template_fingerprint=template_fingerprint, issues=[_issue(error)],
                         admission=admission)
    except ResolutionError as error:
        return _response(psop, template_fingerprint=template_fingerprint, issues=[_issue(error)],
                         admission=admission)

    context, policy = inputs.context, inputs.policy
    scope = f"{context.scope.tenant}/{context.scope.site}/{context.scope.business_object}"

    catalog_issue = None
    try:
        inputs.catalog.validate_workflow(psop)
    except ValueError as error:
        code = str(error).split(":")[0]
        role_task_ids = [t.task_id for s in psop.steps for t in s.subtasks if t.binding == "role"]
        from orchestrate.runtime.role_resolver import ResolutionError as _RE

        catalog_issue = _issue(_RE(code, str(error), task_ids=role_task_ids))

    evaluations, global_error = evaluate_selection_units(
        psop, inputs.registry, inputs.observations, context, policy)
    issues = ([catalog_issue] if catalog_issue is not None else [])
    if global_error is not None:
        issues.append(_issue(global_error))
    units = [_preview_unit(evaluation, context) for evaluation in evaluations]
    for evaluation in evaluations:
        if evaluation.error is not None:
            issues.append(_issue(evaluation.error))

    fingerprint = None
    versions = dict(catalog_version=None, config_version=None, policy_version=None)
    resolvable = (catalog_issue is None
                  and global_error is None
                  and all(evaluation.error is None for evaluation in evaluations))
    if resolvable:
        try:
            result = resolve_role_bindings(
                psop, inputs.catalog, inputs.registry, inputs.observations, context, policy)
            # Preview never allocates the official execution_id; a discarded
            # one is needed only to satisfy the envelope, and is excluded
            # from the confirmation digest.
            snapshot = freeze_resolution_snapshot(
                psop, result, inputs.cards_by_identity, uuid4().hex,
                catalog_fingerprint=inputs.catalog_fingerprint)
            fingerprint = resolution_fingerprint(snapshot, policy)
            versions = dict(catalog_version=result.catalog_version,
                            config_version=result.config_version,
                            policy_version=result.policy_version)
        except (ResolutionError, RoleReferenceError, ValueError) as error:
            issues.append(_issue(error))

    return _response(
        psop, template_fingerprint=template_fingerprint,
        catalog_version=versions["catalog_version"],
        config_version=versions["config_version"],
        policy_version=versions["policy_version"],
        scope=scope, caller_id=context.caller_id,
        units=units, issues=issues,
        can_execute=fingerprint is not None and allowed,
        fingerprint=fingerprint, admission=admission,
    )
