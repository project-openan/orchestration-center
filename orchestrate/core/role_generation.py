# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request-scoped approved catalog and validation for role authoring.

Storage and execution retain their exact-version loaders. This module selects
the configured release for a new template only, and does not consult instances.
"""

import hashlib
import json
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import cached_property
from time import perf_counter
from typing import Literal
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, model_validator

from common.util.json_utils import parse_llm_json_response
from orchestrate.core.catalog_gate import configured_catalog_path
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog, read_role_catalog


class GenerationOptions(BaseModel):
    binding: Literal["instance", "role"] = "instance"
    catalog_version: str | None = Field(None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_mode(self):
        if self.binding == "instance" and self.catalog_version is not None:
            raise ValueError("catalog_version requires binding=role")
        if self.catalog_version is not None and not self.catalog_version.strip():
            raise ValueError("catalog_version must not be blank")
        return self


class RoleGenerationError(ValueError):
    """Caller-safe generation validation failure; never an infrastructure error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class RoleGenerationServiceError(RuntimeError):
    """Model/service failure, separate from invalid generated content."""


def _invalid(message="Model returned an invalid role workflow"):
    return RoleGenerationError("INVALID_GENERATED_WORKFLOW", message)


def _canonical(catalog: RoleCatalog) -> str:
    return json.dumps(catalog.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class RoleGenerationContext:
    # Only immutable JSON is held; projection/model access returns detached data.
    catalog_json: str = field(repr=False)
    entry: str = "generator"
    request_id: str = field(default_factory=lambda: str(uuid4()))

    @cached_property
    def catalog(self) -> RoleCatalog:
        """Parsed once; version, fingerprint and projection treat it as read-only."""
        return RoleCatalog.model_validate_json(self.catalog_json)

    @property
    def catalog_version(self) -> str:
        return self.catalog.catalog_version

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_canonical(self.catalog).encode("utf-8")).hexdigest()

    def projection(self) -> dict:
        catalog = self.catalog
        roles = []
        for role in catalog.roles:
            if role.review_status != "approved":
                continue
            skills = [{key: getattr(skill, key) for key in
                       ("skill_id", "name", "description", "input_summary", "output_summary")
                       if getattr(skill, key) is not None}
                      for skill in role.skills if skill.review_status == "approved"]
            if skills:
                roles.append(dict(role_id=role.role_id, role_version=role.role_version,
                                  name=role.name, description=role.description, skills=skills))
        if not roles:
            raise RoleGenerationError("NO_APPROVED_ROLE_SKILL", "Catalog has no approved role skills")
        return {"catalog_version": catalog.catalog_version, "roles": roles}


def _log_stage(context, stage, started, code):
    logger.info("[RoleGeneration] request_id={} entry={} binding=role catalog_version={} stage={} elapsed_ms={:.1f} result={} code={}",
                context.request_id, context.entry, context.catalog_version, stage,
                (perf_counter() - started) * 1000, "success" if code == "OK" else "failed", code)


@contextmanager
def generation_stage(context: RoleGenerationContext, stage: str):
    started, code = perf_counter(), "OK"
    try:
        yield
    except (RoleGenerationError, RoleGenerationServiceError) as error:
        code = getattr(error, "code", "GENERATION_SERVICE_FAILED")
        raise
    except Exception:
        code = "GENERATION_FAILED"
        raise
    finally:
        _log_stage(context, stage, started, code)


def load_generation_context(expected_version: str | None = None, *, entry="generator", request_id=None) -> RoleGenerationContext:
    started = perf_counter()
    request_id = request_id or str(uuid4())
    path = configured_catalog_path()
    try:
        if not path:
            raise ValueError("No configured catalog")
        catalog = read_role_catalog(path)
        if expected_version is not None and catalog.catalog_version != expected_version:
            raise ValueError("Version mismatch")
    except (OSError, ValueError) as error:
        logger.warning("[RoleGeneration] request_id={} entry={} binding=role catalog_version={!r} stage=catalog elapsed_ms={:.1f} result=rejected code=CATALOG_VERSION_UNAVAILABLE",
                       request_id, entry, expected_version or "unselected", (perf_counter() - started) * 1000)
        raise RoleGenerationError("CATALOG_VERSION_UNAVAILABLE", "Requested catalog release is unavailable") from error
    context = RoleGenerationContext(_canonical(catalog), entry=entry, request_id=request_id)
    with generation_stage(context, "catalog"):
        context.projection()
    return context


def generation_context(binding: str, context: RoleGenerationContext | None = None) -> RoleGenerationContext | None:
    GenerationOptions(binding=binding)
    if binding == "instance":
        if context is not None:
            raise _invalid("Instance generation cannot use role context")
        return None
    context = context or load_generation_context()
    context.projection()
    return context


def validate_current_catalog(context: RoleGenerationContext) -> None:
    """Compare the full release immediately before save; no cross-process transaction is claimed."""
    current = load_generation_context(context.catalog_version, entry=context.entry, request_id=context.request_id)
    if current.fingerprint != context.fingerprint:
        raise RoleGenerationError("CATALOG_VERSION_UNAVAILABLE", "Catalog release changed during generation")


def ask_role_json(llm, prompt: str, context: RoleGenerationContext, stage: str):
    with generation_stage(context, stage):
        try:
            _, response = llm.ask_llm(prompt)
        except Exception as error:
            raise RoleGenerationServiceError("Role generation service failed") from error
        try:
            return parse_llm_json_response(response, redact_errors=True)
        except (ValueError, TypeError) as error:
            raise _invalid("Model returned invalid JSON") from error


def _approved_references(projection):
    return {(role["role_id"], role["role_version"], skill["skill_id"])
            for role in projection["roles"] for skill in role["skills"]}


def _validate_reference(approved, role_id, version, skill_id) -> None:
    try:
        valid = (role_id, version, skill_id) in approved
    except TypeError:
        valid = False
    if not valid:
        raise RoleGenerationError("INVALID_ROLE_SKILL", "Model selected an unapproved role/version/skill reference")


def role_actions(payload) -> list[dict]:
    if not isinstance(payload, list) or not payload or any(not isinstance(action, str) or not action.strip() for action in payload):
        raise _invalid("Action extraction must return a non-empty list of descriptions")
    return [dict(action_id=f"a{index}", description=action) for index, action in enumerate(payload, 1)]


def match_role_actions(payload, actions, context: RoleGenerationContext) -> list[dict]:
    """Validate complete action coverage before assigning server-owned task IDs."""
    if not isinstance(payload, list) or len(payload) != len(actions):
        raise _invalid("Action matching must cover every action exactly once")
    known = {action["action_id"] for action in actions}
    matches = {}
    keys = {"action_id", "role_id", "role_version", "skill_id"}
    approved = _approved_references(context.projection())
    for match in payload:
        if not isinstance(match, dict) or set(match) != keys or any(not isinstance(value, str) for value in match.values()):
            raise _invalid("Invalid role action match")
        action_id = match["action_id"]
        if action_id not in known or action_id in matches:
            raise _invalid("Unknown or duplicate action ID")
        _validate_reference(approved, match["role_id"], match["role_version"], match["skill_id"])
        matches[action_id] = match
    return [dict(task_id=str(uuid4()), description=action["description"], binding="role",
                 agent=matches[action["action_id"]]["role_id"], role_version=matches[action["action_id"]]["role_version"],
                 skill=matches[action["action_id"]]["skill_id"])
            for action in actions]


def assemble_role_workflow(payload, context: RoleGenerationContext, *, expected_tasks=None) -> PSOP:
    """Complete server-owned fields, reject explicit conflicts, then validate again.

    Intentionally invoked more than once per request as defense in depth (no
    LLM cost): right after model output, again after the caller assigns
    server-owned name/user_intent/related_preflow fields, and once more from
    validate_before_save immediately before persistence. Every call re-checks
    references and the task set against the request-scoped catalog snapshot,
    so a late mutation cannot reach storage; do not fold the repeat calls away.
    """
    projection = context.projection()
    version = projection["catalog_version"]
    approved = _approved_references(projection)
    try:
        if not isinstance(payload, dict):
            raise _invalid()
        data = json.loads(json.dumps(payload))
        task_identity_fields = {"binding", "role_version", "binding_group", "task_id"}
        if task_identity_fields.intersection(data):
            raise _invalid("Role binding and task identity fields belong to subtasks")
        if "catalog_version" in data and data["catalog_version"] != version:
            raise RoleGenerationError("CATALOG_VERSION_UNAVAILABLE", "Model returned a conflicting catalog version")
        data["catalog_version"] = version
        data.setdefault("name", "Role Workflow")
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            raise _invalid("Generated workflow has no steps")
        expected = {task["task_id"]: task for task in expected_tasks} if expected_tasks is not None else None
        seen = set()
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("subtasks"), list) or not step["subtasks"]:
                raise _invalid("Generated step has no tasks")
            if task_identity_fields.intersection(step):
                raise _invalid("Role binding and task identity fields belong to subtasks")
            for task in step["subtasks"]:
                if not isinstance(task, dict) or task.get("binding", "role") != "role":
                    raise _invalid("Generated tasks must use role binding")
                task["binding"] = "role"
                if expected is None:
                    task.setdefault("task_id", str(uuid4()))
                identity = task.get("task_id")
                if not isinstance(identity, str) or not identity.strip() or identity in seen:
                    raise _invalid("Generated task IDs must be non-empty and unique")
                seen.add(identity)
                if expected is not None:
                    selected = expected.get(identity)
                    if selected is None or any(task.get(key) != selected[key] for key in
                                               ("agent", "role_version", "skill", "description")):
                        raise _invalid("Structure generation changed the selected task set or identity")
                _validate_reference(approved, task.get("agent"), task.get("role_version"), task.get("skill"))
                if task.get("status", "pending") != "pending":
                    raise _invalid("Generated tasks must start pending")
        if expected is not None and seen != set(expected):
            raise _invalid("Structure generation omitted selected tasks")
        workflow = PSOP.model_validate(data)
        names = [step.name for step in workflow.steps]
        if len(set(names)) != len(names) or any(not name.strip() or name in {"end", "END", "endNode", "END_OF_WORKFLOW"} for name in names):
            raise _invalid("Generated step names must be unique and non-reserved")
        targets = set(names) | {"end", "END", "endNode", "END_OF_WORKFLOW"}
        for step in workflow.steps:
            if any(link.step not in targets for link in step.next or []):
                raise _invalid("Generated workflow has unknown next references")
            if any(name not in set(names) | {"*"} for name in step.context_from or []):
                raise _invalid("Generated workflow has unknown context references")
        context.catalog.validate_workflow(workflow)
        return workflow
    except RoleGenerationError:
        raise
    except (ValidationError, ValueError, TypeError, KeyError) as error:
        raise _invalid() from error
