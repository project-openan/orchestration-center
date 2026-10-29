# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Regression evidence for the role execution contract review."""

import json
import subprocess
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from a2a.types import AgentCard, TaskState
from fastapi import Request
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict, ParseDict
from loguru import logger
from pydantic import ValidationError
from starlette.responses import JSONResponse
from workflow_engine import A2AStreamEvent

from host_agent.config import HostAgentConfig
from host_agent.role_contract import RoleBinding
from host_agent.dispatch_auth import PROOF_KEY, DispatchValidationError, sign_dispatch, verify_dispatch
from host_agent.role_snapshot import validate_role_snapshot
from host_agent.runtime import HostAgentExecutor
from host_agent.service import create_agent_app
from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.core.model.psop import PSOP, Step
from orchestrate.core.model.role_execution_snapshot import RoleExecutionSnapshot, content_digest, freeze_role_execution
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.runtime.exec_engine import OrchestrationEngine
from orchestrate.server import external_api, frontend_support_server
from orchestrate.server.sse_executor import dispatch_intent_sse
from samples.role_pilot.technical_server import TechnicalExecutor, pilot_card
from test_exec_engine_resolution import _approved_catalog_file, _registry_file, _role_psop
from test_host_role_snapshot import INTENT, KEY, Queue, RoutingPolicy, context, envelope, executor, serving
from test_role_pilot_delivery import prepared


@pytest.mark.parametrize("group", ["", " ", "\t\n"])
def test_binding_group_still_rejects_blank_values(group):
    template, result, _ = prepared()
    template.steps[0].subtasks[0].binding_group = group
    with pytest.raises(ValidationError):
        PSOP.model_validate(template.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        RoleBinding.model_validate({**result.bindings[0], "binding_group": group})


@pytest.mark.parametrize("field", ["binding_group", "step_name", "role_task_id", "legacy_task_id"])
@pytest.mark.parametrize("length", [1024, 1025])
def test_freezing_preserves_psop_string_boundaries(field, length):
    template, result, cards = prepared()
    value = "x" * length
    if field == "binding_group":
        template.steps[0].subtasks[0].binding_group = value
        result.bindings[0]["binding_group"] = value
    elif field == "step_name":
        template.steps[0].name = result.execution_psop.steps[0].name = value
    elif field == "role_task_id":
        template.steps[0].subtasks[0].task_id = value
        result.execution_psop.steps[0].subtasks[0].task_id = value
        result.bindings[0]["task_id"] = value
    else:
        legacy = Step.model_validate(dict(name="legacy", subtasks=[dict(
            task_id=value, agent="legacy-agent", skill="legacy-skill", description="Legacy call")]))
        template.steps.append(legacy)
        result.execution_psop.steps.append(deepcopy(legacy))
    template = PSOP.model_validate(template.model_dump(mode="json"))
    result.execution_psop = PSOP.model_validate(result.execution_psop.model_dump(mode="json"))
    snapshot = freeze_role_execution(template, result, cards, "execution-boundary", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
    _, metadata = envelope(snapshot)
    validate_role_snapshot(metadata, snapshot.execution_psop.model_dump(mode="json"),
                           [ParseDict(cards[0].card, AgentCard())])
    assert snapshot.template.model_dump(mode="json") == template.model_dump(mode="json")


@pytest.mark.parametrize("change", ["execution_id", "authorization_type", "scope_wildcard", "unknown_field"])
def test_host_rejects_malformed_envelope_even_when_hashes_are_recomputed(change):
    snapshot, metadata = envelope()
    payload = json.loads(metadata["__orch_cards__"])
    if change == "execution_id":
        del payload["execution_id"]
    elif change == "authorization_type":
        payload["context"]["authorized_instance_ids"] = "technical-a"
    elif change == "scope_wildcard":
        payload["context"]["scope"]["site"] = "*"
        projection = json.loads(metadata["__orch_binding__"])
        projection["scope"] = "technical-demo/*/ran-a"
        metadata["__orch_binding__"] = json.dumps(projection)
    else:
        payload["undeclared"] = "unexpected"
    payload["fingerprint"] = content_digest({key: value for key, value in payload.items() if key != "fingerprint"})
    metadata["__orch_cards__"] = json.dumps(payload)
    with pytest.raises(ValidationError):
        RoleExecutionSnapshot.model_validate(payload)
    with pytest.raises(DispatchValidationError):
        validate_role_snapshot(metadata, snapshot.execution_psop.model_dump(mode="json"),
                               [ParseDict(snapshot.cards[0].card, AgentCard())])


def test_wire_contract_cold_import_does_not_initialize_host_runtime():
    result = subprocess.run([sys.executable, "-c",
        "import sys; import host_agent.role_contract; assert 'host_agent.runtime' not in sys.modules"],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_missing_registry_cards_still_persists_a_failed_execution(monkeypatch):
    template, _, _ = prepared()
    records = []
    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler", lambda _: SimpleNamespace(handle=records.append))
    response = await dispatch_intent_sse([], INTENT, psop=template)
    events = [json.loads(frame.removeprefix("data: ")) async for frame in response.body_iterator]
    assert len(records) == 1
    assert records[0].status == ExecutionStatus.FAILED
    assert records[0].psop_id == template.id
    assert events[0]["data"]["execution_id"] == records[0].execution_id


@pytest.mark.asyncio
async def test_schema_rejection_logs_safe_reason_without_payload_or_key():
    _, metadata = envelope()
    payload = json.loads(metadata["__orch_cards__"])
    payload["private_extra"] = "synthetic-sensitive-payload-must-not-be-logged"
    metadata["__orch_cards__"] = json.dumps(payload)
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    host, queue, messages = executor([]), Queue(), []
    sink = logger.add(messages.append, format="{message}")
    try:
        await host.execute(context(metadata), queue)
    finally:
        logger.remove(sink)
    error = json.loads(queue.events[-1].metadata["__sdk_event__"])["data"]
    assert error["reason"] == "ENVELOPE_SCHEMA"
    assert KEY not in "".join(messages)
    assert payload["private_extra"] not in "".join(messages)
    assert "reason=ENVELOPE_SCHEMA" in "".join(messages)
    host._agent_card_provider.load.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_role_workflow_keeps_real_legacy_login_and_bearer_transport():
    login_calls, business_headers = [], []
    scope = {"tenant": "technical-demo", "site": "city-a", "business_object": "ran-a"}
    token = "synthetic-legacy-session"

    def secured_card(port):
        payload = MessageToDict(pilot_card("b", port))
        payload["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
        payload["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
        return ParseDict(payload, AgentCard())

    def legacy_app(port):
        app = create_agent_app(secured_card(port), TechnicalExecutor("b", scope=scope))

        @app.post("/login")
        async def login(request: Request):
            login_calls.append(await request.json())
            return {"accessSession": token}

        @app.middleware("http")
        async def check_token(request, call_next):
            if request.url.path.startswith("/message"):
                business_headers.append(request.headers.get("Authorization"))
                if business_headers[-1] != f"Bearer {token}":
                    return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            return await call_next(request)

        return app

    with serving(lambda port: create_agent_app(pilot_card("a", port), TechnicalExecutor("a"))) as port_a, serving(legacy_app) as port_b:
        template, result, frozen = prepared(port_a, port_b)
        legacy = Step.model_validate(dict(name="legacy", subtasks=[dict(
            task_id="legacy", agent="Technical RAN B", skill="Explore B", description="Legacy authenticated call")]))
        template.steps.append(legacy)
        result.execution_psop.steps.append(deepcopy(legacy))
        snapshot = freeze_role_execution(template, result, frozen, "execution-with-auth", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
        _, metadata = envelope(snapshot)
        credentials = {"Technical RAN B": {"bearer": {"login_url": f"http://127.0.0.1:{port_b}/login",
            "request_fields": {"fixture": "synthetic-login"}, "token_field": "accessSession"}}}
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda context: RoutingPolicy(context.role_execution.scope.model_dump()),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[pilot_card("a", port_a), secured_card(port_b)])),
            credentials_config=credentials,
        )
        queue = Queue()
        await host.execute(context(metadata), queue)
        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        assert login_calls == [{"fixture": "synthetic-login"}]
        assert business_headers and all(value == f"Bearer {token}" for value in business_headers)


@pytest.mark.parametrize("entry", ["internal", "external_id", "external_intent"])
def test_all_execution_apis_sign_resolved_snapshots_and_record_authenticated_caller(monkeypatch, tmp_path, account_session, entry):
    template, records, sent = _role_psop(), [], []
    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", KEY)
    monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: _approved_catalog_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path", lambda: _registry_file(tmp_path))
    monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances", lambda: ["inst-a", "inst-b"])
    monkeypatch.setattr("orchestrate.server.middleware.async_hit", AsyncMock(return_value=True))
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: SimpleNamespace(
        get_psop_by_id=lambda _: template,
        retrieve_psop_by_intent_topn=lambda *_: [SimpleNamespace(workflow_id=template.id, name=template.name)]))
    for module in (external_api, frontend_support_server):
        monkeypatch.setattr(module, "get_agent_cards", AsyncMock(return_value=[pilot_card("a", 1), pilot_card("b", 2)]))
    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler", lambda _: SimpleNamespace(handle=records.append))

    class VerifyingClient:
        async def stream_message(self, _, content):
            verify_dispatch(content.metadata, KEY, intent=content.parts[0].text)
            sent.append(content)
            yield A2AStreamEvent(event_type="task", task_state="TASK_STATE_COMPLETED")

        async def close(self):
            pass

    monkeypatch.setattr(OrchestrationEngine, "_get_engine_client", lambda _: VerifyingClient())
    params = {"scope": "t/s/b", "caller_id": "forged-caller", "user_intent": INTENT}
    with TestClient(frontend_support_server.app, headers=account_session) as client:
        if entry == "external_intent":
            response = client.post("/api/v1/orchestrate/execute", json={"task": INTENT, "scope": "t/s/b", "caller_id": "forged-caller"})
        elif entry == "external_id":
            response = client.get(f"/api/v1/orchestrate/execute/{template.id}", params=params)
        else:
            response = client.get("/rest/v1/orchestrate/execute", params={**params, "psop_id": template.id})
    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]
    assert not [event for event in events if event["type"] == "error"]
    assert len(sent) == len(records) == 1
    assert records[0].status == ExecutionStatus.SUCCESS
    expected_caller = "fixture-admin" if entry == "internal" else "machine:fixture-admin"
    assert records[0].resolution_snapshot["context"]["caller_id"] == expected_caller
    assert template.steps[0].subtasks[0].binding == "role"
