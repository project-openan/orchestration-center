# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy

import pytest
from pydantic import ValidationError

from orchestrate.core.model.instance_binding import (
    InstanceRegistry, ObservedInstance, ResolutionContext, ResolutionPolicy,
    load_instance_registry,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.runtime.role_resolver import ResolutionError, resolve_role_bindings


@pytest.fixture
def case():
    source = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])
    catalog = RoleCatalog.model_validate(dict(catalog_version="test-v1", roles=[dict(
        role_id="optimizer", role_version="1", name="Test optimizer",
        description="Synthetic test role, not a business approval", source=source,
        review_status="approved", skills=[dict(
            skill_id=skill, name=skill, description=skill, source=source,
            review_status="approved",
        ) for skill in ("explore", "fulfill")],
    )]))
    psop = PSOP.model_validate(dict(name="pilot", catalog_version="test-v1", steps=[dict(
        name="step1", subtasks=[dict(
            task_id="t1", description="Explore", binding="role", agent="optimizer",
            role_version="1", skill="explore",
        )],
    )]))
    scope = dict(tenant="operator", site="city-a", business_object="ran-a")
    instances = []
    cards = []
    for key, site, obj, priority in [("a", "city-a", "ran-a", 10), ("b", "city-b", "ran-b", 20)]:
        name, endpoint = f"Optimizer {key}", f"https://{key}.example.test/a2a"
        instances.append(dict(
            instance_id=key, agent_name=name, endpoint=endpoint, enabled=True,
            technical_status="passed", priority=priority,
            scopes=[dict(tenant="operator", site=site, business_object=obj)],
            skills=[dict(role_id="optimizer", role_version="1", skill_id="explore",
                         instance_skill_id=f"explore-{key}", execution_skill=f"Explore {key}")],
        ))
        cards.append(ObservedInstance(
            instance_id=key, agent_name=name, endpoint=endpoint,
            skills={f"explore-{key}": f"Explore {key}"}, prerequisites_passed=True,
        ))
    return dict(psop=psop, catalog=catalog,
                registry=InstanceRegistry(config_version="config-v1", instances=instances),
                observations=cards,
                context=ResolutionContext(caller_id="test-user", scope=scope, authorized_instance_ids={"a", "b"}),
                policy=ResolutionPolicy(policy_version="policy-v1"))


def same_scope(case):
    case["registry"].instances[1].scopes = deepcopy(case["registry"].instances[0].scopes)


def test_cross_site_mapping_preserves_template(case):
    before = case["psop"].model_dump()
    result = resolve_role_bindings(**case)
    assert result.bindings[0]["instance_id"] == "a"
    assert result.bindings[0]["exclusions"]["b"] == ["OUT_OF_SCOPE"]
    assert result.execution_psop.steps[0].subtasks[0].skill == "Explore a"
    case["context"].scope.site = "city-b"
    case["context"].scope.business_object = "ran-b"
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "b"
    assert case["psop"].model_dump() == before


@pytest.mark.parametrize("field,value,reason", [
    ("enabled", False, "TECHNICAL_ADMISSION_REQUIRED"),
    ("technical_status", "pending", "TECHNICAL_ADMISSION_REQUIRED"),
    ("endpoint", "https://changed.example.test", "INSTANCE_SNAPSHOT_MISMATCH"),
])
def test_invalid_instance_is_excluded(case, field, value, reason):
    setattr(case["registry"].instances[0], field, value)
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert error.value.code == "NO_ELIGIBLE_INSTANCE"
    assert reason in error.value.exclusions["a"]
    assert error.value.task_ids == ["t1"]


def test_authorization_is_hard_filter(case):
    case["context"].authorized_instance_ids.clear()
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert "NOT_AUTHORIZED" in error.value.exclusions["a"]


def test_override_cannot_escape_scope(case):
    case["policy"].task_overrides["t1"] = "b"
    with pytest.raises(ResolutionError, match="INVALID_OVERRIDE"):
        resolve_role_bindings(**case)


def test_override_beats_priority(case):
    same_scope(case)
    case["policy"].task_overrides["t1"] = "a"
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "a"


def test_priority_and_explicit_tie_break(case):
    same_scope(case)
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "b"
    case["registry"].instances[1].priority = 10
    with pytest.raises(ResolutionError, match="AMBIGUOUS_BINDING"):
        resolve_role_bindings(**case)
    case["policy"].tie_break = "instance_id"
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "a"
    case["registry"].instances.reverse()
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "a"


def test_unknown_override_rejected(case):
    case["policy"].task_overrides["typo"] = "a"
    with pytest.raises(ResolutionError, match="INVALID_OVERRIDE"):
        resolve_role_bindings(**case)


def test_missing_card_and_prerequisites(case):
    case["observations"][0].prerequisites_passed = False
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert "PREREQUISITES_NOT_MET" in error.value.exclusions["a"]
    case["observations"].clear()
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert "INSTANCE_NOT_VISIBLE" in error.value.exclusions["a"]


def test_skill_name_must_match_observed_id(case):
    case["observations"][0].skills["explore-a"] = "another skill"
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert "INSTANCE_SKILL_MISMATCH" in error.value.exclusions["a"]


def add_fulfill_task(case, grouped=True):
    first = case["psop"].steps[0].subtasks[0]
    first.binding_group = "session" if grouped else None
    second = first.model_copy(deep=True)
    second.task_id, second.skill = "t2", "fulfill"
    case["psop"].steps[0].subtasks.append(second)


def test_group_requires_skill_union(case):
    add_fulfill_task(case)
    with pytest.raises(ResolutionError, match="BINDING_GROUP_UNSATISFIED"):
        resolve_role_bindings(**case)
    instance = case["registry"].instances[0]
    mapping = instance.skills[0].model_copy(deep=True)
    mapping.skill_id = "fulfill"
    mapping.instance_skill_id, mapping.execution_skill = "fulfill-a", "Fulfill a"
    instance.skills.append(mapping)
    case["observations"][0].skills["fulfill-a"] = "Fulfill a"
    result = resolve_role_bindings(**case)
    assert [r["instance_id"] for r in result.bindings] == ["a", "a"]
    case["policy"].group_overrides["session"] = "a"
    case["policy"].task_overrides["t2"] = "b"
    with pytest.raises(ResolutionError, match="INVALID_OVERRIDE"):
        resolve_role_bindings(**case)


def test_independent_tasks_can_use_different_instances(case):
    same_scope(case)
    add_fulfill_task(case, grouped=False)
    mapping = case["registry"].instances[1].skills[0]
    mapping.skill_id = "fulfill"
    result = resolve_role_bindings(**case)
    assert [r["instance_id"] for r in result.bindings] == ["a", "b"]
    case["registry"].instances[1].agent_name = "Optimizer a"
    case["observations"][1].agent_name = "Optimizer a"
    with pytest.raises(ResolutionError, match="INSTANCE_SNAPSHOT_MISMATCH"):
        resolve_role_bindings(**case)


def test_partial_scope_does_not_form_cartesian_product(case):
    scopes = case["registry"].instances[0].scopes
    scopes.append(scopes[0].model_copy(deep=True))
    scopes[1].site, scopes[1].business_object = "city-b", "ran-b"
    case["context"].scope.business_object = "ran-b"
    with pytest.raises(ResolutionError, match="NO_ELIGIBLE_INSTANCE"):
        resolve_role_bindings(**case)
    scopes[0].business_object = "*"
    assert resolve_role_bindings(**case).bindings[0]["instance_id"] == "a"


def test_context_wildcard_rejected(case):
    case["context"].scope.tenant = "*"
    with pytest.raises(ValidationError, match="concrete"):
        resolve_role_bindings(**case)


def test_registry_roundtrip_and_duplicate_rejected(case, tmp_path):
    path = tmp_path / "instances.json"
    path.write_text(case["registry"].model_dump_json(), encoding="utf-8")
    assert load_instance_registry(path) == case["registry"]
    case["registry"].instances.append(case["registry"].instances[0])
    with pytest.raises(ValidationError, match="Duplicate instance"):
        resolve_role_bindings(**case)


def test_catalog_version_mismatch_is_structured(case):
    case["catalog"].catalog_version = "other"
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert error.value.code == "CATALOG_VERSION_UNAVAILABLE"


def test_mixed_legacy_task_is_preserved(case):
    legacy = case["psop"].steps[0].subtasks[0].model_copy(deep=True)
    legacy.task_id, legacy.agent, legacy.skill = "legacy", "Existing Agent", "Existing Skill"
    legacy.binding, legacy.role_version = "instance", None
    case["psop"].steps[0].subtasks.append(legacy)
    result = resolve_role_bindings(**case)
    assert result.execution_psop.steps[0].subtasks[1] == legacy
    assert len(result.bindings) == 1
    legacy.agent = "Optimizer a"
    with pytest.raises(ResolutionError, match="INSTANCE_SNAPSHOT_MISMATCH"):
        resolve_role_bindings(**case)


def test_same_skill_name_in_another_role_does_not_match(case):
    role = case["catalog"].roles[0].model_copy(deep=True)
    role.role_id = "another-role"
    case["catalog"].roles.append(role)
    case["psop"].steps[0].subtasks[0].agent = "another-role"
    with pytest.raises(ResolutionError) as error:
        resolve_role_bindings(**case)
    assert "MISSING_ROLE_SKILL" in error.value.exclusions["a"]


def test_duplicate_observations_rejected(case):
    case["observations"].append(case["observations"][0])
    with pytest.raises(ResolutionError, match="INSTANCE_SNAPSHOT_MISMATCH"):
        resolve_role_bindings(**case)


def test_group_override_and_result_are_independent(case):
    case["psop"].steps[0].subtasks[0].binding_group = "session"
    same_scope(case)
    case["policy"].group_overrides["session"] = "a"
    result = resolve_role_bindings(**case)
    assert result.bindings[0]["selection_reason"] == "explicit_override"
    result.execution_psop.steps[0].subtasks[0].agent = "changed"
    result.context.scope.site = "changed"
    assert case["psop"].steps[0].subtasks[0].agent == "optimizer"
    assert case["context"].scope.site == "city-a"


def test_duplicate_mapping_rejected(case):
    instance = case["registry"].instances[0]
    instance.skills.append(instance.skills[0])
    with pytest.raises(ValidationError, match="Duplicate role skill mapping"):
        resolve_role_bindings(**case)
