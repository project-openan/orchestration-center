# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Dispatch-side assembly: scope parsing, config fallback, projection, frozen plans."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrate.core.model.instance_binding import (
    InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
)
from orchestrate.core.model.execution_record import ExecutionRecord, ExecutionStatus
from orchestrate.core.model.psop import PSOP
from orchestrate.persistence.errors import RoleReferenceError
from orchestrate.runtime.instance_projection import (
    ResolutionError, ResolutionRequest, build_context_and_policy,
    configured_authorized_instances, configured_execution_scope,
    configured_registry_path, parse_scope, project_observations,
    resolve_execution_plan,
)
from samples.role_pilot.technical_server import pilot_card


@pytest.fixture(autouse=True)
def server_authorization(monkeypatch):
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                        lambda: ["inst-a", "inst-b", "inst-1"])


def test_parse_scope_splits_three_parts():
    scope = parse_scope("operator-a/city-a/ran-domain-a")
    assert scope == ServiceScope(tenant="operator-a", site="city-a", business_object="ran-domain-a")


def test_parse_scope_rejects_wrong_part_count():
    with pytest.raises(ResolutionError) as exc:
        parse_scope("operator-a/city-a")
    assert exc.value.code == "RESOLUTION_INPUT_INVALID"


def test_build_context_requires_scope(monkeypatch):
    monkeypatch.setattr(
        "orchestrate.runtime.instance_projection.configured_execution_scope",
        lambda: None,
    )
    with pytest.raises(ResolutionError) as exc:
        build_context_and_policy(ResolutionRequest())
    assert exc.value.code == "RESOLUTION_INPUT_INVALID"


def test_build_context_prefers_request_over_config(monkeypatch):
    monkeypatch.setattr(
        "orchestrate.runtime.instance_projection.configured_execution_scope",
        lambda: "cfg-t/cfg-s/cfg-b",
    )
    context, policy = build_context_and_policy(ResolutionRequest(
        scope="req-t/req-s/req-b",
        authorized_instance_ids=["inst-1"],
        caller_id="tester",
    ))
    assert context.scope.tenant == "req-t"
    assert context.authorized_instance_ids == {"inst-1"}
    assert context.caller_id == "orchestration-center"


def test_build_context_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(
        "orchestrate.runtime.instance_projection.configured_execution_scope",
        lambda: "cfg-t/cfg-s/cfg-b",
    )
    monkeypatch.setattr(
        "orchestrate.runtime.instance_projection.configured_authorized_instances",
        lambda: ["inst-a", "inst-b"],
    )
    context, policy = build_context_and_policy(ResolutionRequest())
    assert context.scope == ServiceScope(tenant="cfg-t", site="cfg-s", business_object="cfg-b")
    assert context.authorized_instance_ids == {"inst-a", "inst-b"}
    assert context.caller_id == "orchestration-center"


def test_build_policy_defaults():
    context, policy = build_context_and_policy(ResolutionRequest(scope="t/s/b"))
    assert policy.policy_version == "policy-v1"
    assert policy.tie_break == "error"
    assert policy.task_overrides == {} and policy.group_overrides == {}


def _card(name, url, skill_ids):
    from google.protobuf.json_format import ParseDict
    from a2a.types import AgentCard
    return ParseDict(dict(name=name, supportedInterfaces=[dict(url=url, protocolBinding="HTTP+JSON")],
                          skills=[dict(id=sid, name=sid) for sid in skill_ids]), AgentCard())


def _multi_interface_card(name, interfaces, skill_ids, url=None):
    from google.protobuf.json_format import ParseDict
    from a2a.types import AgentCard
    payload = dict(name=name, supportedInterfaces=interfaces,
                   skills=[dict(id=sid, name=sid) for sid in skill_ids])
    if url is not None:
        payload["url"] = url
    return ParseDict(payload, AgentCard())


def _auth_card(name, url, skill_ids, schemes=None, requirements=None, required_extension=None):
    from google.protobuf.json_format import MessageToDict, ParseDict
    from a2a.types import AgentCard
    payload = MessageToDict(_card(name, url, skill_ids))
    if schemes is not None:
        payload["securitySchemes"] = schemes
    if requirements is not None:
        payload["securityRequirements"] = requirements
    if required_extension is not None:
        payload["capabilities"] = {"extensions": [dict(uri=required_extension, required=True)]}
    return ParseDict(payload, AgentCard())


def _registry_with_endpoint(endpoint):
    return InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="agent-a", endpoint=endpoint,
            enabled=True, technical_status="passed",
            scopes=[ServiceScope(tenant="t", site="s", business_object="b")],
            skills=[SkillMapping(role_id="r", role_version="v1", skill_id="sk",
                                 instance_skill_id="exp-a", execution_skill="exp-a")],
        ),
    ])


def _registry():
    return InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="agent-a", endpoint="http://a:1",
            enabled=True, technical_status="passed",
            scopes=[ServiceScope(tenant="t", site="s", business_object="b")],
            skills=[SkillMapping(role_id="r", role_version="v1", skill_id="sk",
                                 instance_skill_id="exp-a", execution_skill="exp-a")],
        ),
        InstanceBinding(
            instance_id="inst-b", agent_name="agent-b", endpoint="http://b:2",
            enabled=True, technical_status="passed",
            scopes=[ServiceScope(tenant="t", site="s", business_object="b")],
            skills=[SkillMapping(role_id="r", role_version="v1", skill_id="sk",
                                 instance_skill_id="exp-b", execution_skill="exp-b")],
        ),
    ])


def test_projection_matches_by_name_and_endpoint():
    cards = [_card("agent-a", "http://a:1", ["exp-a"]), _card("agent-b", "http://other", ["exp-b"])]
    observed = project_observations(_registry(), cards)
    assert [o.instance_id for o in observed] == ["inst-a"]
    assert observed[0].skills == {"exp-a": "exp-a"}
    assert observed[0].prerequisites_passed is True


def test_projection_skips_missing_cards():
    assert project_observations(_registry(), []) == []


def _iface(url, binding="HTTP+JSON"):
    return dict(url=url, protocolBinding=binding)


def test_projection_accepts_multi_interface_card_with_pinned_endpoint():
    card = _multi_interface_card("agent-a", [
        _iface("http://a:0"), _iface("http://a:1"), _iface("http://a:2", "GRPC")], ["exp-a"])
    observed = project_observations(_registry(), [card])
    assert [o.instance_id for o in observed] == ["inst-a"]
    assert observed[0].prerequisites_passed is True


def test_projection_malformed_interface_url_excludes_only_that_candidate():
    broken = _multi_interface_card("agent-a", [_iface("http://a:1"), _iface("http://[broken", "GRPC")], ["exp-a"])
    healthy = _card("agent-b", "http://b:2", ["exp-b"])
    observed = project_observations(_registry(), [broken, healthy])
    assert {o.instance_id: o.prerequisites_passed for o in observed} == {"inst-a": False, "inst-b": True}


@pytest.mark.parametrize("variant", ["additional_grpc", "additional_http", "pinned"])
def test_projection_rejects_embedded_interface_credentials(variant):
    if variant == "additional_grpc":
        endpoint, interfaces = "http://a:1", [_iface("http://a:1"), _iface("http://u:p@a:2", "GRPC")]
    elif variant == "additional_http":
        endpoint, interfaces = "http://a:1", [_iface("http://a:1"), _iface("http://u:p@a:2")]
    else:
        endpoint, interfaces = "http://u:p@a:1", [_iface("http://u:p@a:1")]
    card = _multi_interface_card("agent-a", interfaces, ["exp-a"])
    observed = project_observations(_registry_with_endpoint(endpoint), [card])
    assert observed and not observed[0].prerequisites_passed


@pytest.mark.parametrize("mutation", ["missing_schemes", "undeclared_reference"])
def test_projection_rejects_incomplete_auth_declaration(mutation):
    if mutation == "missing_schemes":
        card = _auth_card("agent-a", "http://a:1", ["exp-a"],
                          requirements=[{"schemes": {"bearer": {"list": []}}}])
    else:
        card = _auth_card("agent-a", "http://a:1", ["exp-a"],
                          schemes={"real": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
                          requirements=[{"schemes": {"ghost": {"list": []}}}])
    observed = project_observations(_registry(), [card])
    assert observed and not observed[0].prerequisites_passed


def test_projection_accepts_complete_auth_and_required_extensions():
    card = _auth_card("agent-a", "http://a:1", ["exp-a"],
                      schemes={"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
                      requirements=[{"schemes": {"bearer": {"list": []}}}],
                      required_extension="urn:example")
    observed = project_observations(_registry(), [card])
    assert observed and observed[0].prerequisites_passed is True


@pytest.mark.parametrize("variant", ["single_grpc", "matches_grpc_only"])
def test_projection_rejects_endpoint_without_http_json_match(variant):
    if variant == "single_grpc":
        card = _multi_interface_card("agent-a", [_iface("http://a:1", "GRPC")], ["exp-a"])
    else:
        card = _multi_interface_card("agent-a", [_iface("http://a:2"), _iface("http://a:1", "GRPC")], ["exp-a"])
    observed = project_observations(_registry(), [card])
    assert observed and not observed[0].prerequisites_passed


def test_multi_interface_card_registers_all_declared_endpoints():
    from orchestrate.runtime.instance_projection import _cards_by_identity
    card = _multi_interface_card("agent-a", [_iface("http://a:1"), _iface("http://a:2", "GRPC")], ["exp-a"])
    identities = _cards_by_identity([card])
    assert set(identities) == {("agent-a", "http://a:1"), ("agent-a", "http://a:2")}


def test_conflicting_identity_across_overlapping_endpoints_rejected():
    from orchestrate.runtime.instance_projection import _cards_by_identity
    first = _multi_interface_card("agent-a", [_iface("http://a:1"), _iface("http://a:2")], ["exp-a"])
    second = _multi_interface_card("agent-a", [_iface("http://a:2")], ["exp-b"])
    with pytest.raises(ResolutionError, match="Conflicting duplicate"):
        _cards_by_identity([first, second])
    assert len(_cards_by_identity([first, first])) == 2


SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
OPTIMIZER = "ran-energy-optimizer"


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


def _registry_file(tmp_path):
    scope = ServiceScope(tenant="t", site="s", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
        InstanceBinding(
            instance_id="inst-b", agent_name="Technical RAN B", endpoint="http://127.0.0.1:2",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="fulfill-energy-intent",
                                 instance_skill_id="explore-b", execution_skill="Explore B")],
        ),
    ])
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    return str(path)


def _role_psop():
    return PSOP.model_validate(dict(
        id="wf-role-pilot", name="Role pilot", catalog_version="pilot-wireless-v1",
        steps=[dict(name="explore", subtasks=[dict(
            task_id="t1", description="Explore energy intent", binding="role",
            agent=OPTIMIZER, skill="explore-energy-intent", role_version="1.0.0",
        )])],
    ))


def _plain_psop():
    return PSOP.model_validate(dict(
        id="wf-plain", name="Plain",
        steps=[dict(name="work", subtasks=[dict(
            task_id="t1", description="Do work", binding="instance",
            agent="Legacy Agent", skill="Legacy Skill",
        )])],
    ))


def test_resolve_execution_plan_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    psop = _role_psop()
    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])
    cards = [pilot_card("a", 1), pilot_card("b", 2)]
    snapshot = resolve_execution_plan(psop, request, cards)
    assert snapshot.execution_psop.id == psop.id
    assert all(task.binding == "instance"
               for step in snapshot.execution_psop.steps for task in step.subtasks)
    assert snapshot.execution_psop.catalog_version is None
    assert snapshot.bindings and snapshot.cards
    assert snapshot.execution_id


def test_resolve_execution_plan_requires_role_tasks():
    with pytest.raises(ResolutionError) as exc:
        resolve_execution_plan(_plain_psop(), ResolutionRequest(scope="t/s/b"), [])
    assert exc.value.code == "RESOLUTION_INPUT_INVALID"


def test_resolve_execution_plan_requires_registry(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: None)
    with pytest.raises(ResolutionError) as exc:
        resolve_execution_plan(_role_psop(), ResolutionRequest(scope="t/s/b"), [])
    assert exc.value.code == "RESOLUTION_INPUT_INVALID"


def test_resolve_execution_plan_catalog_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: None)
    with pytest.raises(RoleReferenceError) as exc:
        resolve_execution_plan(_role_psop(), ResolutionRequest(scope="t/s/b"), [])
    assert "CATALOG_VERSION_UNAVAILABLE" in str(exc.value)


def test_execution_record_accepts_resolution_trace_fields():
    record = ExecutionRecord(
        psop_id="p1", psop_name="n", status=ExecutionStatus.SUCCESS,
        catalog_version="pilot-wireless-v1", config_version="cfg-v1",
        policy_version="policy-v1", execution_scope="t/s/b",
        bindings=[{"task_id": "t1"}], card_fingerprints=["abc123"],
    )
    assert record.catalog_version == "pilot-wireless-v1"
    assert record.bindings == [{"task_id": "t1"}]
    assert record.card_fingerprints == ["abc123"]


def test_execution_record_trace_fields_default_none():
    record = ExecutionRecord(psop_id="p1", psop_name="n", status=ExecutionStatus.SUCCESS)
    assert record.catalog_version is None and record.bindings is None
    assert record.execution_scope is None and record.card_fingerprints is None
    assert record.config_version is None and record.policy_version is None


def test_config_readers_ignore_whitespace_only_values(monkeypatch):
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {
        "role_execution_scope": "   ", "role_registry_path": "  ",
    })
    assert configured_execution_scope() is None
    assert configured_registry_path() is None


def test_authorized_instances_split_and_trim(monkeypatch):
    monkeypatch.setattr(
        "common.util.config_util.get_conf",
        lambda: {"role_authorized_instances": " a , b "},
    )
    assert configured_authorized_instances() == ["a", "b"]


def test_request_cannot_expand_server_authorization():
    with pytest.raises(ResolutionError, match="exceed server authorization"):
        build_context_and_policy(ResolutionRequest(scope="t/s/b", authorized_instance_ids=["forbidden"]))


def test_explicit_empty_authorization_does_not_fall_back():
    context, _ = build_context_and_policy(ResolutionRequest(scope="t/s/b", authorized_instance_ids=[]))
    assert context.authorized_instance_ids == set()


def test_identity_comes_from_authenticated_middleware():
    from orchestrate.runtime.instance_projection import bind_resolution_identity
    from orchestrate.server.auth import SessionIdentity
    request = SimpleNamespace(state=SimpleNamespace(user_identity=SessionIdentity("actual-user", "user")))
    resolution = bind_resolution_identity(ResolutionRequest(scope="t/s/b", caller_id="claimed-admin"), request)
    context, _ = build_context_and_policy(resolution)
    assert context.caller_id == "actual-user"


@pytest.mark.parametrize("mixed", [False, True])
def test_freeze_repeated_instance_and_mixed_template(monkeypatch, tmp_path, mixed):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path", lambda: _registry_file(tmp_path))
    psop = _role_psop()
    first = psop.steps[0].subtasks[0]
    if mixed:
        psop.steps[0].subtasks.append(_plain_psop().steps[0].subtasks[0].model_copy(update={"task_id": "legacy"}))
    else:
        first.binding_group = "shared"
        psop.steps[0].subtasks.append(first.model_copy(update={"task_id": "t2"}, deep=True))
    original = psop.model_dump(mode="json")
    snapshot = resolve_execution_plan(psop, ResolutionRequest(scope="t/s/b"), [pilot_card("a", 1)])
    assert len(snapshot.cards) == 1
    assert len(snapshot.bindings) == (1 if mixed else 2)
    assert psop.model_dump(mode="json") == original
    assert snapshot.bindings[0].selection_reason == "highest_priority"
    assert snapshot.bindings[0].candidates == ["inst-a"]
    if mixed:
        assert snapshot.execution_psop.steps[0].subtasks[1] == psop.steps[0].subtasks[1]


def test_conflicting_duplicate_cards_rejected():
    from orchestrate.runtime.instance_projection import _cards_by_identity
    first, second = pilot_card("a", 1), pilot_card("a", 1)
    second.skills[0].name = "Changed skill"
    with pytest.raises(ResolutionError, match="Conflicting duplicate"):
        _cards_by_identity([first, second])
    assert len(_cards_by_identity([first, first])) == 1


def _resolved_snapshot(monkeypatch, tmp_path, request, psop=None, cards=None):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    return resolve_execution_plan(psop or _role_psop(), request,
                                  cards if cards is not None else [pilot_card("a", 1), pilot_card("b", 2)])


def test_confirmation_digest_mismatch_refuses_resolution(monkeypatch, tmp_path):
    from orchestrate.core.model.role_execution_snapshot import resolution_fingerprint

    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])
    snapshot = _resolved_snapshot(monkeypatch, tmp_path, request)
    policy = build_context_and_policy(request)[1]
    digest = resolution_fingerprint(snapshot, policy)

    # A caller-authorized narrowing changes the confirmed context: refuse.
    narrowed = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a"],
                                 confirm_fingerprint=digest)
    with pytest.raises(ResolutionError) as exc:
        _resolved_snapshot(monkeypatch, tmp_path, narrowed)
    assert exc.value.code == "RESOLUTION_MISMATCH"


def test_confirmation_digest_covers_catalog_content(monkeypatch, tmp_path):
    """A same-version catalog edit invalidates the confirmed arrangement (REQ74 F5)."""
    from orchestrate.core.catalog_gate import load_approved_catalog
    from orchestrate.core.model.role_execution_snapshot import content_digest, resolution_fingerprint

    catalog_path = _approved_catalog_file(tmp_path)
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: catalog_path)
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])
    snapshot = resolve_execution_plan(_role_psop(), request, [pilot_card("a", 1)])
    assert snapshot.catalog_fingerprint == content_digest(
        load_approved_catalog(catalog_path, snapshot.catalog_version, subject="test").model_dump(mode="json"))
    digest = resolution_fingerprint(snapshot, build_context_and_policy(request)[1])

    # Same version, same approval states, edited description of a referenced
    # skill: the catalog content digest differs, so the old digest is refused.
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    for role in data["roles"]:
        for skill in role["skills"]:
            if skill["skill_id"] == "explore-energy-intent":
                skill["description"] = "Edited routing evidence description"
    Path(catalog_path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    confirmed = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"],
                                  confirm_fingerprint=digest)
    with pytest.raises(ResolutionError) as exc:
        resolve_execution_plan(_role_psop(), confirmed, [pilot_card("a", 1)])
    assert exc.value.code == "RESOLUTION_MISMATCH"


def test_confirmation_digest_garbage_never_matches(monkeypatch, tmp_path):
    request = ResolutionRequest(scope="t/s/b", confirm_fingerprint="0" * 64)
    with pytest.raises(ResolutionError) as exc:
        _resolved_snapshot(monkeypatch, tmp_path, request)
    assert exc.value.code == "RESOLUTION_MISMATCH"


def test_confirmation_digest_match_freezes_the_dispatched_arrangement(monkeypatch, tmp_path):
    """On a matching digest the same frozen envelope flows on to dispatch."""
    from orchestrate.core.model.role_execution_snapshot import resolution_fingerprint

    # PSOP.created_at feeds the template fingerprint: the confirmed re-resolve
    # must read the same stored workflow object, as production would.
    psop = _role_psop()
    request = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"])
    snapshot = _resolved_snapshot(monkeypatch, tmp_path, request, psop=psop)
    policy = build_context_and_policy(request)[1]
    digest = resolution_fingerprint(snapshot, policy)

    confirmed = ResolutionRequest(scope="t/s/b", authorized_instance_ids=["inst-a", "inst-b"],
                                  confirm_fingerprint=digest)
    again = _resolved_snapshot(monkeypatch, tmp_path, confirmed, psop=psop)
    # A fresh official execution_id is allocated, but the arrangement is identical.
    assert again.execution_id != snapshot.execution_id
    assert resolution_fingerprint(again, build_context_and_policy(confirmed)[1]) == digest
    assert [b.model_dump(mode="json") for b in again.bindings] == \
        [b.model_dump(mode="json") for b in snapshot.bindings]


def test_execution_record_accepts_confirmation_trace_fields():
    record = ExecutionRecord(
        psop_id="p1", psop_name="n", status=ExecutionStatus.FAILED,
        confirm_fingerprint="a" * 64,
        overrides_applied={"task_overrides": {"t1": "inst-b"}, "group_overrides": {},
                           "tie_break": None},
    )
    assert record.confirm_fingerprint == "a" * 64
    assert record.overrides_applied["task_overrides"] == {"t1": "inst-b"}
    plain = ExecutionRecord(psop_id="p1", psop_name="n", status=ExecutionStatus.SUCCESS)
    assert plain.confirm_fingerprint is None and plain.overrides_applied is None
