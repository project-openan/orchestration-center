# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Execution preview: shared rules, full diagnostics, no dispatch side effects."""

import json
import re
from pathlib import Path

import pytest

from orchestrate.core.model.instance_binding import (
    InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.runtime.instance_projection import ResolutionRequest, resolve_execution_plan
from orchestrate.runtime.role_preview import build_role_preview
from samples.role_pilot.technical_server import pilot_card

SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
OPTIMIZER = "ran-energy-optimizer"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(autouse=True)
def server_authorization(monkeypatch):
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                        lambda: ["inst-a", "inst-b"])
    # Test isolation: a developer-local role_execution_scope must not leak in.
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_execution_scope",
                        lambda: None)


def _approve_all(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "review_status":
                value[key] = "approved"
            else:
                _approve_all(item)
    elif isinstance(value, list):
        for item in value:
            _approve_all(item)


def _approved_catalog_file(tmp_path):
    data = json.loads(SEED_CATALOG.read_text(encoding="utf-8"))
    _approve_all(data)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _registry_file(tmp_path, *, same_scope=False, equal_priority=False):
    """Both instances serve the same role skill so they can replace each
    other; scopes separate them by site unless ``same_scope`` merges them."""
    scope_a = ServiceScope(tenant="t", site="city-a", business_object="b")
    scope_b = scope_a.model_copy(deep=True) if same_scope else ServiceScope(
        tenant="t", site="city-b", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed",
            priority=20 if not equal_priority else 10, scopes=[scope_a],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
        InstanceBinding(
            instance_id="inst-b", agent_name="Technical RAN B", endpoint="http://127.0.0.1:2",
            enabled=True, technical_status="passed",
            priority=10 if not equal_priority else 10, scopes=[scope_b],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-b", execution_skill="Explore B")],
        ),
    ])
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    return str(path)


def _role_psop(**extra_tasks):
    tasks = [dict(
        task_id="t1", description="Explore energy intent", binding="role",
        agent=OPTIMIZER, skill="explore-energy-intent", role_version="1.0.0",
    )]
    tasks.extend(extra_tasks.values())
    return PSOP.model_validate(dict(
        id="wf-role-pilot", name="Role pilot", catalog_version="pilot-wireless-v1",
        steps=[dict(name="explore", subtasks=tasks)],
    ))


def _preview(tmp_path, monkeypatch, request, psop=None, *, same_scope=False, equal_priority=False):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path, same_scope=same_scope,
                                               equal_priority=equal_priority))
    cards = [pilot_card("a", 1), pilot_card("b", 2)]
    return build_role_preview(psop or _role_psop(), request, cards)


def _issue_codes(preview):
    return [issue.code for issue in preview.issues]


def test_preview_resolves_units_with_fingerprint(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"))

    assert preview.can_execute is True
    assert _HEX64.match(preview.resolution_fingerprint)
    assert preview.execution_scope == "t/city-a/b"
    assert preview.catalog_version == "pilot-wireless-v1"
    assert preview.config_version == "cfg-v1"
    assert preview.psop_id == "wf-role-pilot"
    assert preview.template_fingerprint
    assert not any(issue for issue in preview.issues)

    unit = preview.units[0]
    assert unit.unit_id == "task:t1"
    assert unit.task_ids == ["t1"]
    assert unit.required_skills[0].role_id == OPTIMIZER
    assert unit.required_skills[0].skill_id == "explore-energy-intent"
    assert unit.current_selection.instance_id == "inst-a"
    assert unit.current_selection.selection_reason == "highest_priority"
    assert [c.instance_id for c in unit.candidates] == ["inst-a"]
    assert [(e.instance_id, e.reasons) for e in unit.exclusions] == [
        ("inst-b", ["OUT_OF_SCOPE"])]
    # No per-execution identity in a preview: the official execution_id is
    # allocated only by formal resolution.
    assert "execution_id" not in preview.model_dump(mode="json")


def test_preview_scope_changes_the_arrangement(monkeypatch, tmp_path):
    city_a = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"))
    city_b = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-b/b"))

    assert city_a.units[0].current_selection.instance_id == "inst-a"
    assert city_b.units[0].current_selection.instance_id == "inst-b"
    assert city_a.resolution_fingerprint != city_b.resolution_fingerprint


def test_preview_collects_diagnostics_across_units(monkeypatch, tmp_path):
    # t1 resolves via inst-a; t2's fulfillment skill has no candidate at all.
    psop = _role_psop(t2=dict(
        task_id="t2", description="Fulfill", binding="role",
        agent=OPTIMIZER, skill="fulfill-energy-intent", role_version="1.0.0",
    ))
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"), psop)

    assert _issue_codes(preview) == ["NO_ELIGIBLE_INSTANCE"]
    assert preview.issues[0].task_ids == ["t2"]
    assert preview.can_execute is False
    assert preview.resolution_fingerprint is None
    by_task = {unit.task_ids[0]: unit for unit in preview.units}
    # The healthy unit still carries its diagnostics.
    assert by_task["t1"].current_selection.instance_id == "inst-a"
    assert by_task["t2"].current_selection is None
    assert by_task["t2"].candidates == []


def test_preview_hides_unauthorized_instances(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch,
                       ResolutionRequest(scope="t/city-a/b", authorized_instance_ids=["inst-a"]))
    dumped = json.dumps(preview.model_dump(mode="json"))

    assert "inst-b" not in dumped
    assert "Technical RAN B" not in dumped
    assert "127.0.0.1:2" not in dumped
    unit = preview.units[0]
    assert [c.instance_id for c in unit.candidates] == ["inst-a"]
    aggregate = [e for e in unit.exclusions if e.instance_id is None]
    assert len(aggregate) == 1
    assert aggregate[0].reasons == ["NOT_AUTHORIZED"]
    assert all(e.instance_id != "inst-b" for e in unit.exclusions)


def test_preview_ambiguous_still_lists_candidates(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"),
                       same_scope=True, equal_priority=True)

    assert _issue_codes(preview) == ["AMBIGUOUS_BINDING"]
    assert preview.can_execute is False
    assert preview.resolution_fingerprint is None
    assert [c.instance_id for c in preview.units[0].candidates] == ["inst-a", "inst-b"]
    assert preview.units[0].current_selection is None

    resolved = _preview(tmp_path, monkeypatch,
                        ResolutionRequest(scope="t/city-a/b", tie_break="instance_id"),
                        same_scope=True, equal_priority=True)
    assert resolved.can_execute is True
    assert resolved.units[0].current_selection.instance_id == "inst-a"
    assert resolved.units[0].current_selection.selection_reason == "instance_id_tie_break"


def test_preview_override_selects_with_reason(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch,
                       ResolutionRequest(scope="t/city-a/b", tie_break="instance_id"),
                       same_scope=True, equal_priority=True)

    assert preview.units[0].current_selection.instance_id == "inst-a"
    assert preview.units[0].current_selection.selection_reason == "instance_id_tie_break"

    overridden = _preview(tmp_path, monkeypatch,
                          ResolutionRequest(scope="t/city-a/b", tie_break="instance_id",
                                            task_overrides={"t1": "inst-b"}),
                          same_scope=True, equal_priority=True)
    assert overridden.units[0].current_selection.instance_id == "inst-b"
    assert overridden.units[0].current_selection.selection_reason == "explicit_override"


def test_preview_rejects_invalid_overrides(monkeypatch, tmp_path):
    unknown = _preview(tmp_path, monkeypatch,
                       ResolutionRequest(scope="t/city-a/b", task_overrides={"missing": "inst-a"}))
    assert _issue_codes(unknown) == ["INVALID_OVERRIDE"]
    assert unknown.can_execute is False

    out_of_scope = _preview(tmp_path, monkeypatch,
                            ResolutionRequest(scope="t/city-a/b", task_overrides={"t1": "inst-b"}))
    assert _issue_codes(out_of_scope) == ["INVALID_OVERRIDE"]
    assert out_of_scope.units[0].current_selection is None


def test_preview_fingerprint_is_stable_and_sensitive(monkeypatch, tmp_path):
    # One saved template object: re-reading must not change the digest. The
    # template's own created_at is part of its content fingerprint, so a
    # re-saved template legitimately requires a new preview.
    psop = _role_psop()
    first = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"), psop)
    second = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"), psop)
    assert first.resolution_fingerprint == second.resolution_fingerprint

    overridden = _preview(tmp_path, monkeypatch,
                          ResolutionRequest(scope="t/city-a/b", tie_break="instance_id",
                                            task_overrides={"t1": "inst-a"}), psop)
    assert overridden.resolution_fingerprint != first.resolution_fingerprint


def test_preview_fingerprint_matches_formal_resolution(monkeypatch, tmp_path):
    """Preview and formal resolution must derive the same confirmation digest,
    even though only formal resolution allocates an official execution_id."""
    from orchestrate.core.model.instance_binding import ResolutionPolicy
    from orchestrate.core.model.role_execution_snapshot import resolution_fingerprint

    request = ResolutionRequest(scope="t/city-a/b", authorized_instance_ids=["inst-a", "inst-b"])
    psop = _role_psop()
    preview = _preview(tmp_path, monkeypatch, request, psop)
    assert preview.can_execute is True

    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    snapshot = resolve_execution_plan(psop, request, [pilot_card("a", 1), pilot_card("b", 2)])
    policy = ResolutionPolicy(policy_version="policy-v1")

    assert resolution_fingerprint(snapshot, policy) == preview.resolution_fingerprint
    assert snapshot.fingerprint != preview.resolution_fingerprint


def test_preview_catalog_unavailable_blocks_execution(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: None)
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    preview = build_role_preview(_role_psop(), ResolutionRequest(scope="t/city-a/b"),
                                 [pilot_card("a", 1)])

    assert _issue_codes(preview) == ["CATALOG_VERSION_UNAVAILABLE"]
    assert preview.can_execute is False
    assert preview.units == []


def test_preview_missing_scope_is_structured(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest())

    assert _issue_codes(preview) == ["RESOLUTION_INPUT_INVALID"]
    assert preview.can_execute is False
    assert preview.units == []


def test_preview_invalid_scope_is_structured(monkeypatch, tmp_path):
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="just-one-part"))

    assert _issue_codes(preview) == ["RESOLUTION_INPUT_INVALID"]


def test_preview_reports_binding_group_as_one_unit(monkeypatch, tmp_path):
    psop = PSOP.model_validate(dict(
        id="wf-grouped", name="Grouped", catalog_version="pilot-wireless-v1",
        steps=[dict(name="pair", subtasks=[
            dict(task_id="t1", description="Explore", binding="role", agent=OPTIMIZER,
                 skill="explore-energy-intent", role_version="1.0.0", binding_group="pair-1"),
            dict(task_id="t2", description="Fulfill", binding="role", agent=OPTIMIZER,
                 skill="fulfill-energy-intent", role_version="1.0.0", binding_group="pair-1"),
        ])],
    ))
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-b/b"), psop)

    assert _issue_codes(preview) == ["BINDING_GROUP_UNSATISFIED"]
    unit = preview.units[0]
    assert unit.unit_id == "group:pair-1"
    assert unit.binding_group == "pair-1"
    assert unit.task_ids == ["t1", "t2"]
    assert preview.issues[0].binding_group == "pair-1"


def test_preview_unresolvable_catalog_reference_blocks_units(monkeypatch, tmp_path):
    """A template referencing an unapproved/draft release surfaces the catalog code."""
    psop = _role_psop()
    psop.catalog_version = "unknown-version"
    preview = _preview(tmp_path, monkeypatch, ResolutionRequest(scope="t/city-a/b"), psop)

    assert _issue_codes(preview)[0].startswith("CATALOG_VERSION_UNAVAILABLE")
    assert preview.can_execute is False
