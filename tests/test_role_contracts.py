# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Role contracts use synthetic approval fixtures, not business approvals."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog, load_role_catalog


@pytest.fixture
def role_workflow(sample_psop_dict):
    data = deepcopy(sample_psop_dict)
    data["catalog_version"] = "test-v1"
    data["steps"][0]["subtasks"][0].update(
        binding="role", agent="ran-optimizer", role_version="1", skill="explore"
    )
    return data


@pytest.fixture
def catalog_data():
    source = {"package": "synthetic", "pdf": "test.pdf", "pdf_pages": [1]}
    return {
        "catalog_version": "test-v1",
        "roles": [{
            "role_id": "ran-optimizer", "role_version": "1",
            "name": "Test RAN optimizer", "description": "Synthetic test role",
            "source": source, "review_status": "approved",
            "skills": [{
                "skill_id": "explore", "name": "Explore",
                "description": "Synthetic exploration", "source": source,
                "review_status": "approved",
            }],
        }],
    }


def test_legacy_default_and_roundtrip(sample_psop_dict):
    psop = PSOP.model_validate(sample_psop_dict)
    assert psop.steps[0].subtasks[0].binding == "instance"
    assert PSOP.model_validate_json(psop.model_dump_json()) == psop


def test_role_roundtrip_and_exact_catalog(tmp_path, role_workflow, catalog_data):
    psop = PSOP.model_validate(role_workflow)
    catalog = RoleCatalog.model_validate(catalog_data)
    path = tmp_path / "catalog.json"
    path.write_text(catalog.model_dump_json(), encoding="utf-8")
    loaded = load_role_catalog(path, "test-v1")
    loaded.validate_workflow(PSOP.model_validate_json(psop.model_dump_json()))
    with pytest.raises(ValueError, match="CATALOG_VERSION_UNAVAILABLE"):
        load_role_catalog(path, "test-v2")


@pytest.mark.parametrize("field", ["role_version", "agent", "skill", "binding_group"])
def test_blank_role_fields_rejected(role_workflow, field):
    role_workflow["steps"][0]["subtasks"][0][field] = " "
    with pytest.raises(ValidationError):
        PSOP.model_validate(role_workflow)


def test_missing_catalog_rejected(role_workflow):
    del role_workflow["catalog_version"]
    with pytest.raises(ValidationError, match="catalog_version"):
        PSOP.model_validate(role_workflow)


def test_role_self_loop_rejected(role_workflow):
    role_workflow["steps"][0]["type"] = "SelfLoop"
    with pytest.raises(ValidationError, match="SelfLoop"):
        PSOP.model_validate(role_workflow)


def test_group_cannot_cross_roles(role_workflow):
    task = role_workflow["steps"][0]["subtasks"][0]
    task["binding_group"] = "same-instance"
    role_workflow["steps"][0]["subtasks"].append(
        {**task, "task_id": "t2", "agent": "another-role"}
    )
    with pytest.raises(ValidationError, match="same role"):
        PSOP.model_validate(role_workflow)


def test_duplicate_task_ids_rejected(role_workflow):
    tasks = role_workflow["steps"][0]["subtasks"]
    tasks.append(deepcopy(tasks[0]))
    with pytest.raises(ValidationError, match="unique task"):
        PSOP.model_validate(role_workflow)


def test_mixed_workflow_allowed(role_workflow, sample_psop_dict):
    task = deepcopy(sample_psop_dict["steps"][0]["subtasks"][0])
    task["task_id"] = "legacy-task"
    role_workflow["steps"][0]["subtasks"].append(task)
    psop = PSOP.model_validate(role_workflow)
    assert [t.binding for t in psop.steps[0].subtasks] == ["role", "instance"]


@pytest.mark.parametrize("target", ["role", "skill"])
def test_draft_definitions_cannot_authorize(role_workflow, catalog_data, target):
    role = catalog_data["roles"][0]
    if target == "role":
        role["review_status"] = "draft"
    else:
        role["skills"].append({**deepcopy(role["skills"][0]), "skill_id": "other"})
        role["skills"][0]["review_status"] = "draft"
    catalog = RoleCatalog.model_validate(catalog_data)
    with pytest.raises(ValueError, match="INVALID_ROLE_SKILL"):
        catalog.validate_workflow(PSOP.model_validate(role_workflow))


def test_duplicate_skill_rejected(catalog_data):
    skills = catalog_data["roles"][0]["skills"]
    skills.append(deepcopy(skills[0]))
    with pytest.raises(ValidationError, match="Duplicate skill"):
        RoleCatalog.model_validate(catalog_data)


def test_optional_io_requires_evidence(catalog_data):
    catalog_data["roles"][0]["skills"][0]["input_summary"] = "A target"
    with pytest.raises(ValidationError, match="summary and source"):
        RoleCatalog.model_validate(catalog_data)


def test_overlong_catalog_text_rejected(catalog_data):
    catalog_data["roles"][0]["description"] = "x" * 1025
    with pytest.raises(ValidationError):
        RoleCatalog.model_validate(catalog_data)


def test_catalog_source_page_bounds(catalog_data):
    source = catalog_data["roles"][0]["source"]
    source["pdf_pages"] = [100001]
    with pytest.raises(ValidationError):
        RoleCatalog.model_validate(catalog_data)
    source["pdf_pages"] = list(range(1, 10002))
    with pytest.raises(ValidationError):
        RoleCatalog.model_validate(catalog_data)
    source["pdf_pages"] = [1, 100000]
    assert RoleCatalog.model_validate(catalog_data).roles[0].source.pdf_pages == [1, 100000]


def test_role_version_not_silently_upgraded(role_workflow, catalog_data):
    catalog_data["roles"][0]["role_version"] = "2"
    with pytest.raises(ValueError, match="INVALID_ROLE_SKILL"):
        RoleCatalog.model_validate(catalog_data).validate_workflow(
            PSOP.model_validate(role_workflow)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [True, False])
async def test_unresolved_roles_never_open_transport(
    monkeypatch, role_workflow, explicit
):
    from types import SimpleNamespace
    from orchestrate.runtime.exec_engine import OrchestrationEngine
    from orchestrate.core.shared_handlers import SharedHandlers

    psop = PSOP.model_validate(role_workflow)
    engine = OrchestrationEngine.__new__(OrchestrationEngine)
    engine._target_agent = "Host Agent"
    engine._agent_cards = []

    def forbidden_client():
        pytest.fail("Unresolved role reached transport construction")

    monkeypatch.setattr(engine, "_get_engine_client", forbidden_client)
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        retrieve_psop_by_intent_topn=lambda *args: [
            SimpleNamespace(workflow_id=psop.id, name=psop.name)
        ],
        get_psop_by_id=lambda _: psop,
    ))
    monkeypatch.setattr(
        "orchestrate.core.catalog_gate.configured_catalog_path", lambda: None,
    )
    events = [event async for event in engine.events("explore", psop=psop if explicit else None)]
    errors = [event for event in events if event["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["data"]["code"] == "CATALOG_VERSION_UNAVAILABLE"
