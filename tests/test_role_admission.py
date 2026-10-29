# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""REQ74 P4: role execution admission -- closed by default, explicit pilot only.

The dispatch signature key authenticates a message; this gate authorizes the
capability. Production and unrecognized environments never admit pilot mode.
"""

import json
from pathlib import Path

import pytest

from host_agent.config import HostAgentConfig
from host_agent import dispatch_auth as _dispatch_auth_module
from host_agent.dispatch_auth import PROOF_KEY
from host_agent.role_contract import role_execution_admitted
from orchestrate.runtime import role_admission as _role_admission_module
from orchestrate.runtime.instance_projection import ResolutionError, ResolutionRequest, resolve_execution_plan
from orchestrate.runtime.role_admission import role_execution_admission
from orchestrate.runtime.role_preview import build_role_preview
from samples.role_pilot.technical_server import pilot_card

SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
OPTIMIZER = "ran-energy-optimizer"

# The conftest autouse fixture replaces the configuration readers; capture the
# real ones at import time for the reader-focused tests below.
_REAL_MODE_READER = _role_admission_module.configured_role_execution_mode
_REAL_ENV_READER = _role_admission_module.configured_deployment_environment
_REAL_HOST_ADMITTED = HostAgentConfig.role_execution_admitted


@pytest.mark.parametrize("mode,environment,expected,reasons", [
    (None, None, False, ["MODE_DISABLED"]),
    ("disabled", "technical_pilot", False, ["MODE_DISABLED"]),
    ("pilot", "production", False, ["ENVIRONMENT_NOT_PERMITTED"]),
    ("pilot", None, False, ["ENVIRONMENT_NOT_PERMITTED"]),
    ("pilot", "staging", False, ["ENVIRONMENT_NOT_PERMITTED"]),
    ("pilot", "PRODUCTION", False, ["ENVIRONMENT_NOT_PERMITTED"]),
    ("pilot", " Technical_Pilot ", True, []),
    ("pilot", "development", True, []),
    ("pilot", "testing", True, []),
    ("always_on", "development", False, ["MODE_INVALID"]),
])
def test_role_execution_admitted_matrix(mode, environment, expected, reasons):
    allowed, rejection = role_execution_admitted(mode, environment)
    assert allowed is expected
    assert rejection == reasons


def test_conf_readers_trim_and_default_to_closed(monkeypatch):
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {
        "role_execution_mode": " pilot ", "deployment_environment": " testing "})
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_role_execution_mode",
                        _REAL_MODE_READER)
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_deployment_environment",
                        _REAL_ENV_READER)
    assert _REAL_MODE_READER() == "pilot"
    assert _REAL_ENV_READER() == "testing"
    allowed, _ = role_execution_admission()
    assert allowed is True


def test_conf_readers_unset_means_closed(monkeypatch):
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {})
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_role_execution_mode",
                        _REAL_MODE_READER)
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_deployment_environment",
                        _REAL_ENV_READER)
    assert _REAL_MODE_READER() is None
    assert _REAL_ENV_READER() is None
    allowed, reasons = role_execution_admission()
    assert allowed is False and reasons == ["MODE_DISABLED"]


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
    from orchestrate.core.model.instance_binding import (
        InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
    )

    scope = ServiceScope(tenant="t", site="s", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
    ])
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    return str(path)


def _role_psop():
    from orchestrate.core.model.psop import PSOP

    return PSOP.model_validate(dict(
        id="wf-role-pilot", name="Role pilot", catalog_version="pilot-wireless-v1",
        steps=[dict(name="explore", subtasks=[dict(
            task_id="t1", description="Explore energy intent", binding="role",
            agent=OPTIMIZER, skill="explore-energy-intent", role_version="1.0.0",
        )])],
    ))


def test_closed_gate_refuses_resolution_before_any_input_work(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_role_execution_mode",
                        lambda: None)
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    with pytest.raises(ResolutionError) as exc:
        resolve_execution_plan(_role_psop(), ResolutionRequest(scope="t/s/b"), [pilot_card("a", 1)])
    assert exc.value.code == "ROLE_EXECUTION_NOT_ENABLED"


def test_preview_reports_admission_and_blocks_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.runtime.role_admission.configured_role_execution_mode",
                        lambda: None)
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    preview = build_role_preview(_role_psop(), ResolutionRequest(scope="t/s/b"), [pilot_card("a", 1)])
    assert preview.execution_admission.allowed is False
    assert preview.execution_admission.reasons == ["MODE_DISABLED"]
    assert preview.can_execute is False
    assert preview.resolution_fingerprint is None


def test_preview_reports_admitted_deployments(monkeypatch, tmp_path):
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                        lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                        lambda: _registry_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                        lambda: ["inst-a"])
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_execution_scope",
                        lambda: None)
    preview = build_role_preview(_role_psop(), ResolutionRequest(scope="t/s/b"), [pilot_card("a", 1)])
    assert preview.execution_admission.allowed is True
    assert preview.execution_admission.reasons == []
    assert preview.can_execute is True


# ═══════════════════════════════════════════════════════════════════════════════
# Host side: the same deployment policy guards the role snapshot path.
# ═══════════════════════════════════════════════════════════════════════════════

def test_host_config_defaults_to_a_closed_gate(monkeypatch):
    monkeypatch.setattr(HostAgentConfig, "role_execution_admitted", _REAL_HOST_ADMITTED)
    config = HostAgentConfig(orchestration_url="http://o", registry_url="http://r")
    assert config.role_execution_mode == "disabled"
    assert config.deployment_environment == "production"
    assert config.role_execution_admitted() == (False, ["MODE_DISABLED"])


@pytest.mark.parametrize("mode,environment,expected", [
    ("pilot", "technical_pilot", True),
    ("pilot", "production", False),
    ("disabled", "development", False),
])
def test_host_config_admission_matrix(monkeypatch, mode, environment, expected):
    monkeypatch.setattr(HostAgentConfig, "role_execution_admitted", _REAL_HOST_ADMITTED)
    config = HostAgentConfig(orchestration_url="http://o", registry_url="http://r",
                             role_execution_mode=mode, deployment_environment=environment)
    allowed, _ = config.role_execution_admitted()
    assert allowed is expected


@pytest.mark.asyncio
async def test_host_runtime_refuses_role_dispatch_on_closed_deployment(monkeypatch):
    """A signed dispatch on a closed host is refused before verification or dispatch."""
    from types import SimpleNamespace

    from host_agent.runtime import HostAgentExecutor

    monkeypatch.setattr(HostAgentConfig, "role_execution_admitted", _REAL_HOST_ADMITTED)
    verified = []
    monkeypatch.setattr(_dispatch_auth_module, "verify_dispatch",
                        lambda *args, **kwargs: verified.append(args))
    dispatched = []
    monkeypatch.setattr("host_agent.runtime.execute_psop",
                        lambda **kwargs: dispatched.append(kwargs))

    async def _noop_iter(**kwargs):
        return
        yield

    monkeypatch.setattr("host_agent.runtime.execute_psop", _noop_iter)
    host = HostAgentExecutor(
        config=HostAgentConfig(orchestration_url="http://o", registry_url="http://r"),
        control_point_factory=lambda context: SimpleNamespace(),
    )

    events = []

    class _Queue:
        async def enqueue_event(self, event):
            events.append(event)

    context = SimpleNamespace(metadata={PROOF_KEY: "payload"}, message=None,
                              get_user_input=lambda: "intent", task_id="t1", context_id="c1")
    await host.execute(context, _Queue())

    assert verified == []
    assert dispatched == []
    error_events = [event for event in events
                    if "ROLE_EXECUTION_NOT_ADMITTED" in str(getattr(event, "metadata", {}))]
    assert error_events, "the refusal must surface as an error task update"


def test_sample_composition_honors_deployment_admission_config(monkeypatch):
    """The real sample composition passes server.conf admission keys through (REQ74 F3)."""
    from samples.spn_host_agent.bootstrap import create_spn_host_executor

    monkeypatch.setattr(HostAgentConfig, "role_execution_admitted", _REAL_HOST_ADMITTED)
    monkeypatch.setattr("samples.spn_host_agent.bootstrap.get_conf",
                        lambda: {"role_execution_mode": "pilot",
                                 "deployment_environment": "technical_pilot"})
    config = create_spn_host_executor([])._config
    assert (config.role_execution_mode, config.deployment_environment) == ("pilot", "technical_pilot")
    assert config.role_execution_admitted() == (True, [])

    monkeypatch.setattr("samples.spn_host_agent.bootstrap.get_conf", lambda: {})
    closed = create_spn_host_executor([])._config
    assert closed.role_execution_admitted() == (False, ["MODE_DISABLED"])
