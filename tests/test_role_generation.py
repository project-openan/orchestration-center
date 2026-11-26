# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from copy import deepcopy

import pytest

from orchestrate.core.intent_psop_generator import IntentPsopGenerator
from orchestrate.core.psop_generator import PsopGenerator
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.role_catalog import load_role_catalog
from orchestrate.core.role_generation import (
    GenerationOptions, RoleGenerationError, RoleGenerationServiceError,
    load_generation_context, validate_current_catalog,
)
from tests.role_generation_helpers import JsonModel, catalog_payload, workflow_payload, action_matches as matches, structure_from_prompt


@pytest.fixture
def release(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    monkeypatch.setattr("orchestrate.core.role_generation.configured_catalog_path", lambda: str(path))
    return path


def intent_generator(model):
    generator = IntentPsopGenerator.__new__(IntentPsopGenerator)
    generator._llm = model
    return generator


def test_projection_is_approved_detached_and_exact_version(release):
    context = load_generation_context()
    projection = context.projection()
    assert projection["catalog_version"] == "generation-v1"
    assert [role["role_id"] for role in projection["roles"]] == ["role-a", "role-b"]
    assert "private-draft" not in json.dumps(projection)
    assert "source" not in json.dumps(projection)
    projection["roles"][0]["skills"].clear()
    assert context.projection()["roles"][0]["skills"]
    with pytest.raises(RoleGenerationError, match="CATALOG_VERSION_UNAVAILABLE"):
        load_generation_context("other-version")
    with pytest.raises(ValueError, match="CATALOG_VERSION_UNAVAILABLE"):
        load_role_catalog(release, None)


@pytest.mark.parametrize("payload,code", [
    (None, "CATALOG_VERSION_UNAVAILABLE"),
    ({"catalog_version": "v", "roles": []}, "NO_APPROVED_ROLE_SKILL"),
    ({**catalog_payload(), "roles": [{**role, "review_status": "draft"} for role in catalog_payload()["roles"]]}, "NO_APPROVED_ROLE_SKILL"),
])
def test_unusable_catalog_fails_before_model(release, payload, code):
    if payload is None:
        release.unlink()
    else:
        release.write_text(json.dumps(payload), encoding="utf-8")
    model = JsonModel(workflow_payload())
    with pytest.raises(RoleGenerationError, match=code):
        intent_generator(model).generate_psop_from_intent("Analyze", [], binding="role")
    assert model.prompts == []


def test_instance_options_do_not_accept_a_catalog_version():
    assert GenerationOptions().binding == "instance"
    with pytest.raises(ValueError):
        GenerationOptions(catalog_version="v1")
    with pytest.raises(ValueError):
        GenerationOptions(binding="unknown")


def test_intent_roles_need_no_instances_and_server_assembles_missing_mode(release):
    payload = workflow_payload()
    del payload["steps"][0]["subtasks"][0]["binding"]
    del payload["steps"][0]["subtasks"][0]["task_id"]
    model = JsonModel(payload)
    workflow = intent_generator(model).generate_psop_from_intent("Analyze", [], "Chosen", binding="role")
    assert workflow.name == "Chosen"
    assert workflow.user_intent == "Analyze"
    assert workflow.catalog_version == "generation-v1"
    assert workflow.steps[0].subtasks[0].binding == "role"
    assert workflow.steps[0].subtasks[0].task_id
    assert "private-draft" not in model.prompts[0]
    assert '"role_id": "role-b"' in model.prompts[0]


@pytest.mark.parametrize("change,code", [
    (lambda p: p.update(catalog_version="other"), "CATALOG_VERSION_UNAVAILABLE"),
    (lambda p: p.update(steps=[]), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p.update(binding="instance"), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0].update(binding="role"), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0].update(binding_group="misplaced"), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0].update(subtasks=[]), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0].update(type="SelfLoop"), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0]["subtasks"][0].update(binding="instance"), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0]["subtasks"][0].update(agent="unknown"), "INVALID_ROLE_SKILL"),
    (lambda p: p["steps"][0]["subtasks"][0].update(role_version="other"), "INVALID_ROLE_SKILL"),
    (lambda p: p["steps"][0]["subtasks"][0].update(skill="private-draft"), "INVALID_ROLE_SKILL"),
    (lambda p: p["steps"][0]["subtasks"].append(deepcopy(p["steps"][0]["subtasks"][0])), "INVALID_GENERATED_WORKFLOW"),
    (lambda p: p["steps"][0].update(next=[{"step": "unknown", "condition": ""}]), "INVALID_GENERATED_WORKFLOW"),
])
def test_intent_rejects_conflicts_and_invalid_templates(release, change, code):
    payload = workflow_payload()
    change(payload)
    with pytest.raises(RoleGenerationError, match=code):
        intent_generator(JsonModel(payload)).generate_psop_from_intent("Analyze", [], binding="role")


def test_catalog_content_change_is_rejected_even_when_version_and_ids_stay_same(release):
    context = load_generation_context()
    payload = catalog_payload()
    payload["roles"][0]["description"] = "Different release content"
    release.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RoleGenerationError, match="CATALOG_VERSION_UNAVAILABLE"):
        validate_current_catalog(context)


def test_model_failure_is_not_a_validation_error(release):
    with pytest.raises(RoleGenerationServiceError):
        intent_generator(JsonModel(RuntimeError("private upstream detail"))).generate_psop_from_intent("Analyze", [], binding="role")


def test_rejection_log_has_request_catalog_stage_and_code_without_business_text(release):
    from loguru import logger

    context = load_generation_context(entry="test_intent")
    payload = workflow_payload()
    payload["steps"][0]["subtasks"][0]["skill"] = "private-draft"
    output = []
    sink = logger.add(lambda message: output.append(str(message)))
    try:
        with pytest.raises(RoleGenerationError):
            intent_generator(JsonModel(payload)).generate_psop_from_intent("private-business-intent", [],
                binding="role", role_context=context)
    finally:
        logger.remove(sink)
    logs = "".join(output)
    for evidence in (context.request_id, "entry=test_intent", "binding=role", "catalog_version=generation-v1",
                     "stage=generate_intent", "code=INVALID_ROLE_SKILL", "elapsed_ms="):
        assert evidence in logs
    assert "private-business-intent" not in logs


def preflow_generator(model):
    generator = PsopGenerator.__new__(PsopGenerator)
    generator._llm = model
    return generator


def test_preflow_preserves_repeated_actions_and_joint_identity_without_name_reverse_lookup(release, monkeypatch):
    model = JsonModel(["Analyze", "Analyze"], matches(), structure_from_prompt)
    generator = preflow_generator(model)
    monkeypatch.setattr(generator, "match_actions_to_skills", lambda *_: pytest.fail("Legacy name lookup used"))
    monkeypatch.setattr(generator, "_normalize_subtask_agents", lambda *_: pytest.fail("Instance normalization used"))
    preflow = PreFlow(name="Input", steps_md="Analyze twice")
    workflow = generator.generate_psop_workflow(preflow, [], binding="role")
    tasks = workflow.steps[0].subtasks
    assert workflow.name == preflow.name and workflow.related_preflow == preflow.id
    assert len(tasks) == 2 and len({task.task_id for task in tasks}) == 2
    assert [task.agent for task in tasks] == ["role-a", "role-b"]
    assert [task.description for task in tasks] == ["Analyze", "Analyze"]
    assert all(task.skill == "explore" for task in tasks)
    assert "private-draft" not in model.prompts[1]


@pytest.mark.parametrize("matching", [
    [], matches()[:1], [matches()[0], matches()[0]],
    [{**matches()[0], "action_id": "unknown"}, matches()[1]],
    [{**matches()[0], "skill_id": "private-draft"}, matches()[1]],
    {"Analyze": "explore"},
])
def test_preflow_rejects_incomplete_duplicate_or_unapproved_action_matching(release, matching):
    model = JsonModel(["Analyze", "Analyze"], matching)
    with pytest.raises(RoleGenerationError):
        preflow_generator(model).generate_psop_workflow(PreFlow(name="Input", steps_md="Analyze"), [], binding="role")
    assert len(model.prompts) == 2


@pytest.mark.parametrize("change", [
    lambda tasks: tasks.pop(),
    lambda tasks: tasks.append(deepcopy(tasks[0])),
    lambda tasks: tasks[0].update(task_id="unselected"),
    lambda tasks: tasks[0].update(agent="role-b"),
    lambda tasks: tasks[0].update(description="Rewritten business action"),
])
def test_preflow_rejects_structural_task_set_and_identity_changes(release, change):
    def changed_structure(prompt):
        payload = structure_from_prompt(prompt)
        change(payload["steps"][0]["subtasks"])
        return payload

    model = JsonModel(["Analyze", "Analyze"], matches(), changed_structure)
    with pytest.raises(RoleGenerationError, match="INVALID_GENERATED_WORKFLOW"):
        preflow_generator(model).generate_psop_workflow(PreFlow(name="Input", steps_md="Analyze"), [], binding="role")
