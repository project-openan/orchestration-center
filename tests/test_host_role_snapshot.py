# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Host admission and real center -> Host -> worker SDK transport coverage."""

import asyncio
import json
import socket
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import uvicorn
from a2a.types import AgentCard, Message, TaskState
from google.protobuf.json_format import MessageToDict, ParseDict
from loguru import logger
from workflow_engine import ControlPoint, MessageContent, StubWorkflowEngineClient, TaskResult, Workflow

from host_agent.dispatch_auth import (
    DISPATCH_KEYS, PROOF_KEY, DispatchValidationError, sign_dispatch, verify_dispatch,
)
from host_agent.config import HostAgentConfig
from host_agent.adapters import DefaultEngineClientFactory
from host_agent.role_snapshot import validate_role_snapshot
from host_agent.runtime import HostAgentExecutor
from host_agent.service import create_agent_app
from orchestrate.core.model.instance_binding import InstanceRegistry
from orchestrate.core.model.card_snapshot import card_fingerprint
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.model.role_execution_snapshot import RoleExecutionSnapshot, content_digest, freeze_role_execution
from orchestrate.runtime.exec_engine import _role_dispatch_metadata
from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.server.sse_executor import dispatch_intent_sse
from orchestrate.runtime.instance_projection import ResolutionRequest
from samples.role_pilot.technical_server import TechnicalExecutor, pilot_card
from test_role_pilot_delivery import prepared


KEY = "synthetic-test-key-for-role-dispatch-only"
INTENT = "run synthetic role workflow"


def envelope(snapshot=None):
    snapshot = snapshot or freeze_role_execution(*prepared(), "execution-1", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
    metadata = {
        "__orch_psop_id__": snapshot.template.id,
        "__orch_psop__": snapshot.execution_psop.model_dump_json(),
        **_role_dispatch_metadata(snapshot),
    }
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    return snapshot, metadata


class Queue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def context(metadata):
    # Exercise the actual protobuf metadata boundary, including nested proof.
    message = ParseDict({"metadata": metadata}, Message())
    return SimpleNamespace(task_id="test-task", context_id="test-context", metadata={},
                           message=message, get_user_input=lambda: INTENT)


def executor(cards):
    return HostAgentExecutor(
        config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused", role_dispatch_key=KEY),
        control_point_factory=lambda _: RoutingPolicy(),
        agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=cards)),
        engine_client_factory=SimpleNamespace(create=Mock()),
    )


@pytest.mark.parametrize("field", [*DISPATCH_KEYS, PROOF_KEY, "intent", "key", "expired", "future"])
def test_dispatch_authentication_rejects_tampering(field):
    _, metadata = envelope()
    key, intent = KEY, INTENT
    if field in DISPATCH_KEYS:
        metadata[field] += "tampered"
    elif field == PROOF_KEY:
        del metadata[PROOF_KEY]
    elif field == "intent":
        intent += " changed"
    elif field == "key":
        key = "a-different-synthetic-key-of-sufficient-length"
    else:
        offset = -301 if field == "expired" else 31
        metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT, now=time.time() + offset)
    with pytest.raises(DispatchValidationError, match="INSTANCE_SNAPSHOT_MISMATCH"):
        verify_dispatch(metadata, key, intent=intent)


def test_authentication_survives_protobuf_and_keeps_key_out_of_config_repr():
    _, metadata = envelope()
    verify_dispatch(HostAgentExecutor._orchestration_metadata(context(metadata)), KEY, intent=INTENT)
    assert KEY not in repr(executor([])._config)
    assert KEY not in json.dumps(metadata)


@pytest.mark.parametrize("key", ["", "short"])
def test_unconfigured_trust_stays_disabled(key):
    _, metadata = envelope()
    with pytest.raises(DispatchValidationError, match="ROLE_EXECUTION_NOT_ENABLED"):
        verify_dispatch(metadata, key, intent=INTENT)


@pytest.mark.parametrize("case,diagnostic", [
    ("missing_proof", "MALFORMED_PROOF"),
    ("missing_signature", "MALFORMED_PROOF"),
    ("invalid_timestamp", "MALFORMED_PROOF"),
    ("wrong_signature", "INVALID_SIGNATURE"),
    ("wrong_key", "INVALID_SIGNATURE"),
    ("tampered_payload", "INVALID_SIGNATURE"),
    ("expired", "EXPIRED_PROOF"),
    ("future", "FUTURE_PROOF"),
    ("tampered_expired", "INVALID_SIGNATURE"),
])
def test_proof_diagnostics_do_not_change_public_errors(case, diagnostic):
    _, metadata = envelope()
    issued = 9699 if case in {"expired", "tampered_expired"} else 10031 if case == "future" else 10000
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT, now=issued)
    key = KEY
    if case == "missing_proof":
        del metadata[PROOF_KEY]
    elif case == "missing_signature":
        del metadata[PROOF_KEY]["signature"]
    elif case == "invalid_timestamp":
        metadata[PROOF_KEY]["issued_at"] = "not-a-timestamp"
    elif case in {"wrong_signature", "tampered_expired"}:
        signature = metadata[PROOF_KEY]["signature"]
        metadata[PROOF_KEY]["signature"] = ("1" if signature[0] == "0" else "0") + signature[1:]
    elif case == "wrong_key":
        key = "another-synthetic-dispatch-key-of-sufficient-length"
    elif case == "tampered_payload":
        metadata["__orch_psop__"] += "tampered"
    with pytest.raises(DispatchValidationError) as failure:
        verify_dispatch(metadata, key, intent=INTENT, now=10000)
    assert failure.value.diagnostic_reason == diagnostic
    assert failure.value.event_data() == {
        "code": "INSTANCE_SNAPSHOT_MISMATCH", "reason": "UNTRUSTED_SOURCE",
        "error": "INSTANCE_SNAPSHOT_MISMATCH: Untrusted role dispatch context",
    }


@pytest.mark.parametrize("issued", [9700, 10000, 10030])
def test_freshness_window_remains_inclusive(issued):
    _, metadata = envelope()
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT, now=issued)
    verify_dispatch(metadata, KEY, intent=INTENT, now=10000)


def test_authenticated_huge_timestamp_is_rejected_without_overflow():
    _, metadata = envelope()
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT, now=10 ** 400)
    with pytest.raises(DispatchValidationError) as failure:
        verify_dispatch(metadata, KEY, intent=INTENT, now=10000)
    assert failure.value.diagnostic_reason == "FUTURE_PROOF"
    assert failure.value.event_data()["reason"] == "UNTRUSTED_SOURCE"


@pytest.mark.asyncio
@pytest.mark.parametrize("case,diagnostic", [
    ("expired", "EXPIRED_PROOF"), ("future", "FUTURE_PROOF"),
    ("signature", "INVALID_SIGNATURE"), ("missing", "MALFORMED_PROOF"),
])
async def test_rejection_logs_internal_reason_without_unverified_identity(case, diagnostic):
    _, metadata = envelope()
    payload = json.loads(metadata["__orch_cards__"])
    marker = "unverified-caller-must-not-be-logged"
    payload["context"]["caller_id"] = marker
    payload["context"]["scope"]["site"] = "unverified-site-must-not-be-logged"
    metadata["__orch_cards__"] = json.dumps(payload)
    offset = -301 if case == "expired" else 31 if case == "future" else 0
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT, now=time.time() + offset)
    if case == "signature":
        metadata[PROOF_KEY]["signature"] = "invalid-synthetic-signature"
    signature = metadata[PROOF_KEY]["signature"]
    if case == "missing":
        del metadata[PROOF_KEY]
    host, queue, messages = executor([]), Queue(), []
    sink = logger.add(messages.append, format="{message}")
    try:
        await host.execute(context(metadata), queue)
    finally:
        logger.remove(sink)
    logs = "".join(messages)
    assert f"diagnostic_reason={diagnostic}" in logs
    assert "caller_id='unverified' scope='unverified'" in logs
    assert marker not in logs
    assert payload["context"]["scope"]["site"] not in logs
    assert KEY not in logs and signature not in logs
    error = json.loads(queue.events[-1].metadata["__sdk_event__"])["data"]
    assert error["reason"] == "UNTRUSTED_SOURCE"
    assert "diagnostic_reason" not in error
    host._agent_card_provider.load.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_present", [True, False])
async def test_host_logs_verified_identity_on_acceptance_and_registry_rejection(registry_present):
    snapshot, metadata = envelope()
    cards = [ParseDict(snapshot.cards[0].card, AgentCard())] if registry_present else []
    host, queue, messages = executor(cards), Queue(), []
    host._engine_client_factory.create.return_value = StubWorkflowEngineClient()
    sink = logger.add(messages.append, format="{message}")
    try:
        await host.execute(context(metadata), queue)
    finally:
        logger.remove(sink)
    outcome = "accepted" if registry_present else "rejected"
    audit = next(message for message in messages if f"[RoleHost] {outcome}" in message)
    assert f"execution_id={snapshot.execution_id}" in audit
    assert f"caller_id={snapshot.context.caller_id!r}" in audit
    scope = snapshot.context.scope
    scope_path = f"{scope.tenant}/{scope.site}/{scope.business_object}"
    assert f"scope={scope_path!r}" in audit
    assert queue.events[-1].status.state == (
        TaskState.TASK_STATE_COMPLETED if registry_present else TaskState.TASK_STATE_FAILED)


@pytest.mark.asyncio
async def test_expanded_candidate_envelope_reaches_engine_factory():
    from host_agent.role_dispatch import TASK_T_URI
    from test_role_contract_candidates import _add_extra_interfaces, _candidate

    def mutate(card):
        _add_extra_interfaces(card)
        card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
        card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
        card["capabilities"] = {"extensions": [{"uri": TASK_T_URI, "required": True}]}

    snapshot, live = _candidate(mutate)
    metadata = {
        "__orch_psop_id__": snapshot.template.id,
        "__orch_psop__": snapshot.execution_psop.model_dump_json(),
        **_role_dispatch_metadata(snapshot),
    }
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    host, queue = executor([live]), Queue()
    host._engine_client_factory.create.return_value = StubWorkflowEngineClient()
    host._credentials_config = {"Technical RAN A": {"bearer": {
        "login_url": "http://127.0.0.1:9/login",
        "request_fields": {"user": "u", "secret": "p"}}}}

    class TaskTRoutingPolicy(RoutingPolicy):
        async def on_task(self, request):
            city = request.skill[-1].lower()
            base = MessageContent.text(json.dumps(
                {"tenant": "technical-demo", "site": f"city-{city}",
                 "business_object": f"ran-{city}", "skill_id": f"explore-{city}"}))
            return MessageContent(parts=base.parts,
                                  metadata={TASK_T_URI: "task-t-payload"},
                                  extensions={TASK_T_URI})

    host._control_point_factory = lambda _: TaskTRoutingPolicy()
    await host.execute(context(metadata), queue)
    host._engine_client_factory.create.assert_called_once()
    # The dispatch projection pins the multi-interface card to its endpoint.
    projected = host._engine_client_factory.create.call_args.args[0]
    assert [interface.url for interface in projected[0].supported_interfaces] == [
        snapshot.cards[0].endpoint]
    assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "endpoint", "skill", "security", "extension", "duplicate"])
async def test_registry_drift_rejected_before_transport(change):
    snapshot, metadata = envelope()
    payload = deepcopy(snapshot.cards[0].card)
    if change == "endpoint":
        payload["supportedInterfaces"][0]["url"] = "http://changed:1"
    elif change == "skill":
        payload["skills"][0]["name"] = "Changed"
    elif change == "security":
        payload["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    elif change == "extension":
        payload["capabilities"] = {"extensions": [{"uri": "urn:changed", "required": True}]}
    cards = [] if change == "missing" else [ParseDict(payload, AgentCard())]
    if change == "duplicate":
        cards.append(ParseDict(payload, AgentCard()))
    host = executor(cards)
    queue = Queue()
    await host.execute(context(metadata), queue)
    host._engine_client_factory.create.assert_not_called()
    assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
    error = json.loads(queue.events[-1].metadata["__sdk_event__"])
    assert error["data"]["code"] == "INSTANCE_SNAPSHOT_MISMATCH"


@pytest.mark.parametrize("change", ["binding", "card_hash", "task", "extra_task", "interface", "skill", "template",
                                   "binding_group", "unauthorized", "duplicate_binding", "duplicate_card", "catalog"])
def test_semantic_mismatch_rejected_even_with_authenticated_metadata(change):
    snapshot, metadata = envelope()
    if change == "binding":
        binding = json.loads(metadata["__orch_binding__"])
        binding["bindings"] = []
        metadata["__orch_binding__"] = json.dumps(binding)
    elif change in {"task", "extra_task"}:
        workflow = json.loads(metadata["__orch_psop__"])
        task = workflow["steps"][0]["subtasks"][0]
        if change == "task":
            task["agent"] = "some other agent"
        else:
            workflow["steps"][0]["subtasks"].append({**task, "task_id": "extra"})
        metadata["__orch_psop__"] = json.dumps(workflow)
    else:
        payload = json.loads(metadata["__orch_cards__"])
        if change == "card_hash":
            payload["cards"][0]["fingerprint"] = "changed"
        elif change == "interface":
            payload["cards"][0]["card"]["supportedInterfaces"].append(
                {"url": "http://other", "protocolBinding": "HTTP+JSON"})
        elif change == "skill":
            payload["bindings"][0]["instance_skill_id"] = "unknown"
        elif change == "binding_group":
            payload["bindings"][0]["binding_group"] = "changed"
        elif change == "unauthorized":
            payload["context"]["authorized_instance_ids"] = []
        elif change == "duplicate_binding":
            payload["bindings"].append(deepcopy(payload["bindings"][0]))
        elif change == "duplicate_card":
            payload["cards"].append(deepcopy(payload["cards"][0]))
        elif change == "catalog":
            payload["catalog_version"] = "other"
        else:
            payload["template"]["steps"][0]["subtasks"] = []
            payload["template_fingerprint"] = content_digest(payload["template"])
        if change == "interface":
            payload["cards"][0]["fingerprint"] = card_fingerprint(payload["cards"][0]["card"])
        projection = {key: payload[key] for key in ("catalog_version", "config_version", "policy_version", "bindings")}
        scope = payload["context"]["scope"]
        projection["scope"] = "/".join(scope[key] for key in ("tenant", "site", "business_object"))
        metadata["__orch_binding__"] = json.dumps(projection)
        payload["fingerprint"] = content_digest({k: v for k, v in payload.items() if k != "fingerprint"})
        metadata["__orch_cards__"] = json.dumps(payload)
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    verify_dispatch(metadata, KEY, intent=INTENT)
    with pytest.raises(DispatchValidationError):
        validate_role_snapshot(metadata, json.loads(metadata["__orch_psop__"]),
                               [ParseDict(snapshot.cards[0].card, AgentCard())])


@pytest.mark.asyncio
async def test_untrusted_metadata_does_not_load_registry_or_resolve_workflow():
    _, metadata = envelope()
    metadata["__orch_psop__"] += "changed"
    host = executor([])
    host._resolve_workflow = AsyncMock()
    queue = Queue()
    await host.execute(context(metadata), queue)
    host._resolve_workflow.assert_not_awaited()
    host._agent_card_provider.load.assert_not_awaited()
    host._engine_client_factory.create.assert_not_called()


def test_conflicting_context_and_message_metadata_rejected():
    _, metadata = envelope()
    request = context(metadata)
    request.metadata = {"__orch_psop_id__": "different"}
    with pytest.raises(DispatchValidationError):
        HostAgentExecutor._orchestration_metadata(request)


def test_legacy_authentication_cards_and_credentials_reach_existing_factory(monkeypatch):
    snapshot, metadata = envelope()
    legacy = MessageToDict(pilot_card("b", 18992))
    legacy["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    legacy_card = ParseDict(legacy, AgentCard())
    verified = validate_role_snapshot(metadata, json.loads(metadata["__orch_psop__"]),
                                     [ParseDict(snapshot.cards[0].card, AgentCard()), legacy_card])
    transport_factory = Mock()
    owning = Mock()
    monkeypatch.setattr("host_agent.adapters.WorkflowEngineClient.owning", owning)
    credentials = {"synthetic-credential-reference": {"login_url": "http://unused/login"}}
    factory = DefaultEngineClientFactory(credentials_config=credentials, ssl_verify=True,
                                          transport_factory=transport_factory)
    factory.create(verified)
    assert verified[-1] is legacy_card
    transport_factory.assert_called_once_with(agent_cards=verified, credentials_config=credentials, ssl_verify=True)
    owning.assert_called_once_with(transport_factory.return_value, max_negotiation_exchanges=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["malformed_workflow", "registry_unavailable"])
async def test_invalid_workflow_or_registry_failure_is_structured(failure):
    _, metadata = envelope()
    host = executor([])
    if failure == "malformed_workflow":
        metadata["__orch_psop__"] = "invalid json"
        metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    else:
        host._agent_card_provider.load.side_effect = RuntimeError("registry unavailable")
    queue = Queue()
    await host.execute(context(metadata), queue)
    host._engine_client_factory.create.assert_not_called()
    error = json.loads(queue.events[-1].metadata["__sdk_event__"])
    assert error["data"]["code"] == "INSTANCE_SNAPSHOT_MISMATCH"


class RoutingPolicy(ControlPoint):
    def __init__(self, scope=None, execution=None):
        self.scope = scope
        self.execution = execution

    async def on_task(self, request):
        # The SDK receives execution skills, never role IDs. Runtime scope is
        # business content produced by the injected policy, not SDK internals.
        if self.execution is not None:
            binding = self.execution.binding_for(request)
            if binding is not None:
                assert (binding.agent, binding.execution_skill) == (request.agent_name, request.skill)
                assert binding.task_id == self.execution.task_identity(request).task_id
        city = request.skill[-1].lower()
        assert request.agent_name == f"Technical RAN {city.upper()}"
        scope = self.scope or {"tenant": "technical-demo", "site": f"city-{city}", "business_object": f"ran-{city}"}
        return MessageContent.text(json.dumps({**scope, "skill_id": f"explore-{city}"}))

    async def on_self_task(self, request):
        if self.execution is not None:
            assert self.execution.binding_for(request) is None
        return TaskResult.succeeded(("local merge",))


@contextmanager
def serving(build_app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_app(port), log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@pytest.mark.asyncio
@pytest.mark.parametrize("generation", ["existing", "intent", "preflow"])
async def test_real_center_host_worker_chain_cross_site_and_replacement(monkeypatch, tmp_path, generation):
    calls, host_cards, sdk_workflows, workers = [], [], [], {}
    records = []
    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler",
                        lambda _: SimpleNamespace(handle=records.append))

    class RecordingWorker(TechnicalExecutor):
        async def execute(self, context, queue):
            calls.append((self.city, json.loads(context.get_user_input())))
            await super().execute(context, queue)

    def worker_app(city):
        workers[city] = RecordingWorker(city)
        return lambda port: create_agent_app(pilot_card(city, port), workers[city])

    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", KEY)
    with serving(worker_app("a")) as port_a, serving(worker_app("b")) as port_b:
        cards = [pilot_card("a", port_a), pilot_card("b", port_b)]
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused"),
            control_point_factory=lambda context: RoutingPolicy(
                context.role_execution.scope.model_dump(), context.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=cards)),
        )
        original_create = host._engine_client_factory.create

        def capture_cards(verified):
            host_cards.append(verified)
            return original_create(verified)

        host._engine_client_factory.create = capture_cards
        import host_agent.runtime as runtime
        original_execute = runtime.execute_psop

        async def capture_workflow(**kwargs):
            sdk_workflows.append(deepcopy(kwargs["psop"]))
            async for event in original_execute(**kwargs):
                yield event

        monkeypatch.setattr(runtime, "execute_psop", capture_workflow)

        def host_app(port):
            card = pilot_card("a", port)
            card.name = "Host Agent"
            card.capabilities.streaming = True
            host_cards.append(card)
            return create_agent_app(card, host)

        catalog_path, registry_path = tmp_path / "catalog.json", tmp_path / "registry.json"
        source = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])
        catalog = RoleCatalog.model_validate(dict(catalog_version="synthetic-v1", roles=[dict(
            role_id="test-optimizer", role_version="1", name="Test", description="Synthetic only",
            source=source, review_status="approved", skills=[dict(skill_id="explore", name="Explore",
            description="Routing echo only", source=source, review_status="approved")])]))
        catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")
        monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path", lambda: str(catalog_path))
        monkeypatch.setattr("orchestrate.core.role_generation.configured_catalog_path", lambda: str(catalog_path))
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path", lambda: str(registry_path))
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances",
                            lambda: ["technical-a", "technical-b"])
        with serving(host_app):
            target_card = host_cards.pop()

            async def collect(template, request):
                response = await dispatch_intent_sse([target_card, *cards], INTENT,
                    target_agent="Host Agent", lang="en", psop=template, resolution_request=request)
                return [json.loads(frame.removeprefix("data: ")) async for frame in response.body_iterator
                        if frame.startswith("data: ")]

            base_template, _, _ = prepared(port_a, port_b)
            from orchestrate.core.catalog_gate import CatalogGate
            from orchestrate.core.persistence import WorkflowStorage
            store = WorkflowStorage(str(tmp_path / "generated-store"))
            if generation != "existing":
                from orchestrate.core.intent_psop_generator import IntentPsopGenerator
                from orchestrate.core.psop_generator import PsopGenerator
                from orchestrate.core.model.preflow import PreFlow
                from orchestrate.core.role_generation import load_generation_context, validate_current_catalog
                from tests.role_generation_helpers import JsonModel, structure_from_prompt

                if generation == "intent":
                    generator = IntentPsopGenerator.__new__(IntentPsopGenerator)
                    generator._llm = JsonModel(base_template.model_dump(mode="json"))
                    base_template = generator.generate_psop_from_intent(INTENT, [], binding="role")
                else:
                    generator = PsopGenerator.__new__(PsopGenerator)
                    generator._llm = JsonModel(["Explore"], [dict(action_id="a1", role_id="test-optimizer",
                        role_version="1", skill_id="explore")], structure_from_prompt)
                    base_template = generator.generate_psop_workflow(PreFlow(name="Generated", steps_md="Explore"), [], binding="role")
                validate_current_catalog(load_generation_context())
            CatalogGate(SimpleNamespace(handle=store.save_psop)).handle(base_template)
            base_template = store.load_psop(base_template.id)
            base_template_json = base_template.model_dump_json()
            for scenario in ("city-a", "city-b", "replacement", "mixed"):
                city = "a" if scenario in {"city-a", "mixed"} else "b"
                template = base_template
                if scenario == "mixed":
                    payload = template.model_dump(mode="json")
                    payload["steps"][0]["next"] = [{"step": "legacy", "condition": ""}]
                    payload["steps"].extend([
                        dict(name="legacy", subtasks=[dict(task_id="legacy", agent="Technical RAN B",
                             skill="Explore B", description="Legacy task")], next=[dict(step="merge", condition="")]),
                        dict(name="merge", type="SelfLoop", subtasks=[dict(task_id="local", agent="Host Agent",
                             skill="merge", description="Local merge")]),
                    ])
                    template = PSOP.model_validate(payload)
                original_template = template.model_dump_json()
                instances = []
                for key, card in zip(("a", "b"), cards):
                    scope = {"tenant": "technical-demo", "site": f"city-{key}", "business_object": f"ran-{key}"}
                    if scenario in {"replacement", "mixed"}:
                        scope = {"tenant": "technical-demo", "site": "city-a", "business_object": "ran-a"}
                    workers[key].scope = scope
                    instances.append(dict(instance_id=f"technical-{key}", agent_name=card.name,
                        endpoint=card.supported_interfaces[0].url, enabled=not (
                            scenario == "replacement" and key == "a" or scenario == "mixed" and key == "b"),
                        technical_status="passed", scopes=[scope], skills=[dict(role_id="test-optimizer", role_version="1",
                        skill_id="explore", instance_skill_id=f"explore-{key}", execution_skill=f"Explore {key.upper()}")]))
                registry_path.write_text(InstanceRegistry(config_version=scenario, instances=instances).model_dump_json(), encoding="utf-8")
                scope_city = "a" if scenario == "replacement" else city
                request = ResolutionRequest(scope=f"technical-demo/city-{scope_city}/ran-{scope_city}")
                events = await asyncio.wait_for(collect(template, request), timeout=20)
                assert not [event for event in events if event["type"] == "error"], events
                assert any(event["type"] == "complete" for event in events)
                resolution = next(event for event in events if event["type"] == "resolution")
                snapshot = RoleExecutionSnapshot.model_validate(resolution["data"]["resolution_snapshot"])
                assert records[-1].execution_id == snapshot.execution_id
                assert records[-1].status == ExecutionStatus.SUCCESS
                assert records[-1].snapshot_fingerprint == snapshot.fingerprint
                if scenario == "mixed":
                    assert [key for key, _ in calls[-2:]] == ["a", "b"]
                    completed = [event for event in events if event["type"] == "step_complete"]
                    assert any(event["data"]["step"] == "merge" for event in completed)
                else:
                    assert calls[-1][0] == city
                assert calls[-1][1]["site"] == f"city-{scope_city}"
                assert host_cards[-1][0] is not cards[0 if city == "a" else 1]
                assert MessageToDict(host_cards[-1][0]) == snapshot.cards[0].card
                assert sdk_workflows[-1] == Workflow.from_dict(snapshot.execution_psop.model_dump(mode="json"))
                assert all(not hasattr(task, "binding") for step in sdk_workflows[-1].steps for task in step.subtasks)
                assert template.model_dump_json() == original_template
            assert [city for city, _ in calls] == ["a", "b", "b", "a", "b"]
            assert base_template.model_dump_json() == base_template_json
            assert store.load_psop(base_template.id).model_dump_json() == base_template_json
            changed = deepcopy(cards[0])
            changed.skills[0].name = "Changed after center freeze"
            host._agent_card_provider.load.return_value = [changed, cards[1]]
            before_calls, before_factories = len(calls), len(host_cards)
            events = await asyncio.wait_for(collect(base_template,
                ResolutionRequest(scope="technical-demo/city-a/ran-a")), timeout=20)
            error = next(event["data"] for event in events if event["type"] == "error")
            assert error["code"] == "INSTANCE_SNAPSHOT_MISMATCH"
            assert error["reason"] == "REGISTRY_CARD_DRIFT"
            assert error["task_ids"] == [base_template.steps[0].subtasks[0].task_id]
            assert error["instance_id"] == "technical-a"
            assert records[-1].execution_id == error["execution_id"]
            assert records[-1].status == ExecutionStatus.FAILED
            assert len(calls) == before_calls
            assert len(host_cards) == before_factories
