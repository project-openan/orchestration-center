# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Seventh batch unit B: host dispatch adaptation for expanded candidates.

Endpoint projection pins the SDK to the registry-selected interface; the
engine-client wrapper enforces the extension four-check and the
authentication pre-check before dispatch, converts dispatch failures into
structured BusinessFailure errors, and validates provider output at send
time. Legacy instance tasks keep their batch-5 behavior.
"""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from a2a.types import AgentCard, TaskState
from google.protobuf.json_format import ParseDict
from workflow_engine import (
    BusinessFailure, ControlPoint, EventType, MessageContent, NegotiationRequest,
    NegotiationSend, ReceivedMessage, StubWorkflowEngineClient,
)

from host_agent.config import HostAgentConfig, RoleExecutionContext
from host_agent.dispatch_auth import PROOF_KEY, DispatchValidationError, sign_dispatch
from host_agent.role_dispatch import (
    NEGOTIATION_T_URI, ROLE_DISPATCH_FAILED, RoleDispatchEngineClient, SUPPORTED_EXTENSIONS, TASK_T_URI,
    ValidatingAuthProvider, _dispatch_identity, project_dispatch_interfaces,
)
from host_agent.role_execution import RoleExecutionBridge
from host_agent.runtime import HostAgentExecutor
from orchestrate.runtime.exec_engine import _role_dispatch_metadata
from test_host_role_snapshot import INTENT, KEY, Queue, context, executor
from test_role_contract_candidates import _add_extra_interfaces, _candidate


class FakeEngineClient:
    """Records dispatches and lifecycle calls; optionally raises."""

    def __init__(self, exc=None):
        self.dispatched = []
        self.exc = exc
        self.begun = []
        self.ended = []
        self.closed = False

    @property
    def callback_timeout_seconds(self):
        return 30

    def begin_execution(self, execution_id, control_point, event_callback):
        self.begun.append(execution_id)

    def end_execution(self, execution_id):
        self.ended.append(execution_id)

    async def dispatch(self, request, content, callbacks=None):
        self.dispatched.append((request, content))
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(sentinel="dispatch-result")

    async def close(self):
        self.closed = True


class Provider:
    """AuthProvider double that writes fixed headers or raises."""

    def __init__(self, headers=None, exc=None):
        self.headers = dict(headers or {})
        self.exc = exc
        self.calls = []

    def apply_auth(self, agent_name, agent_card, headers):
        self.calls.append(agent_name)
        if self.exc is not None:
            raise self.exc
        headers.update(self.headers)


class ProviderCallingClient(FakeEngineClient):
    """Calls the wrapped provider during dispatch, like the SDK transport."""

    def __init__(self, provider):
        super().__init__()
        self.provider = provider
        self.auth_headers = []

    async def dispatch(self, request, content, callbacks=None):
        headers = {}
        self.provider.apply_auth(request.agent_name,
                                 ParseDict({"name": request.agent_name}, AgentCard()),
                                 headers)
        self.auth_headers.append(headers)
        return await super().dispatch(request, content, callbacks)


class NegotiationClient(FakeEngineClient):
    """Drives one negotiation exchange like the SDK's engine client."""

    def __init__(self):
        super().__init__()
        self.sent = []

    async def dispatch(self, request, content, callbacks=None):
        self.sent.append(frozenset(getattr(content, "extensions", None) or ()))
        received = ReceivedMessage(message=content)
        reply = await callbacks.on_negotiation(NegotiationRequest(
            task=request, original_submission=content, received=received,
            previous_exchanges=(), remaining_wait_seconds=30.0,
        ))
        if isinstance(reply, NegotiationSend):
            self.sent.append(frozenset(reply.content.extensions or ()))
        return SimpleNamespace(sentinel="dispatch-result")


class NegotiationPolicy(ControlPoint):
    """Answers every negotiation request with a fixed reply content."""

    def __init__(self, reply):
        self.reply = reply
        self.negotiations = 0

    async def on_task(self, request):
        return MessageContent.text(request.instruction)

    async def on_negotiation(self, request):
        self.negotiations += 1
        return NegotiationSend(self.reply)


def task_t_card(card):
    card["capabilities"] = {"extensions": [{"uri": TASK_T_URI, "required": True}]}


def unknown_required_card(card):
    card["capabilities"] = {"extensions": [{"uri": "urn:unknown-required", "required": True}]}


def auth_card(card):
    card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]


def alternative_auth_card(card):
    # Bearer or API key: either requirement alone satisfies the card.
    card["securitySchemes"] = {
        "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
        "key": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}},
    }
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}},
                                    {"schemes": {"key": {"list": []}}}]


def combined_auth_card(card):
    # Bearer and API key together in one requirement: both are needed.
    card["securitySchemes"] = {
        "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
        "key": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}},
    }
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []},
                                                 "key": {"list": []}}}]


COMPLETE_CREDENTIALS = {"bearer": {"login_url": "http://127.0.0.1:9/login",
                                   "request_fields": {"user": "u", "secret": "p"}}}


def content(extensions=(), metadata=None):
    base = MessageContent.text("business content")
    return MessageContent(parts=base.parts, metadata=metadata or {},
                          extensions=frozenset(extensions))


def harness(mutate=lambda card: None, *, credentials=None, provider=None, inner=None):
    """Bridge-registered context and wrapper around a controllable client."""
    snapshot, live = _candidate(mutate)
    workflow = snapshot.execution_psop.model_dump(mode="json")
    step = workflow["steps"][0]
    task = step["subtasks"][0]
    raw_context = RoleExecutionContext(
        execution_id=snapshot.execution_id,
        caller_id=snapshot.context.caller_id,
        scope=snapshot.context.scope,
        bindings=tuple(snapshot.bindings),
    )
    bridge = RoleExecutionBridge(raw_context, workflow)
    bridge.observe({"type": EventType.TASK_REQUEST, "data": {
        "execution_id": "sdk-execution", "task_id": "sdk-task",
        "step": step["name"], "subtask_index": 0, "agent": task["agent"],
    }})
    request = SimpleNamespace(execution_id="sdk-execution", task_id="sdk-task",
                              step_name=step["name"], agent_name=task["agent"],
                              skill=task["skill"])
    client = inner if inner is not None else FakeEngineClient()
    wrapper = RoleDispatchEngineClient(client, bridge.context, snapshot,
                                       credentials=credentials, auth_provider=provider)
    return SimpleNamespace(snapshot=snapshot, live=live, workflow=workflow,
                           request=request, inner=client, wrapper=wrapper)


def bearer_card_dict():
    return {"name": "Technical RAN A",
            "securitySchemes": {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
            "securityRequirements": [{"schemes": {"bearer": {"list": []}}}]}


def api_key_card_dict():
    return {"name": "Technical RAN A",
            "securitySchemes": {
                "key": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}}},
            "securityRequirements": [{"schemes": {"key": {"list": []}}}]}


def cookie_key_card_dict():
    return {"name": "Technical RAN A",
            "securitySchemes": {
                "key": {"apiKeySecurityScheme": {"location": "cookie", "name": "session"}}},
            "securityRequirements": [{"schemes": {"key": {"list": []}}}]}


def bearer_key_card_dict():
    return {"name": "Technical RAN A",
            "securitySchemes": {
                "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
                "key": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}}},
            "securityRequirements": [{"schemes": {"bearer": {"list": []},
                                                  "key": {"list": []}}}]}


def alternative_requirements_card_dict():
    card = bearer_key_card_dict()
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}},
                                    {"schemes": {"key": {"list": []}}}]
    return card


@contextmanager
def validated_dispatch(agent="Technical RAN A", execution_id="execution-x", **identity):
    """Simulate the in-flight auth-requiring role dispatch the provider gates on."""
    token = _dispatch_identity.set({"agent": agent, "execution_id": execution_id, **identity})
    try:
        yield
    finally:
        _dispatch_identity.reset(token)


# ---------------------------------------------------------------------------
# Endpoint projection
# ---------------------------------------------------------------------------

def test_projection_pins_the_selected_interface_and_leaves_others_untouched():
    snapshot, live = _candidate(_add_extra_interfaces)
    legacy = ParseDict({"name": "Legacy Agent"}, AgentCard())
    projected = project_dispatch_interfaces(snapshot, [live, legacy])
    assert projected[1] is legacy
    pinned = projected[0]
    frozen = snapshot.cards[0]
    assert [interface.url for interface in pinned.supported_interfaces] == [frozen.endpoint]
    assert all(interface.protocol_binding == "HTTP+JSON"
               for interface in pinned.supported_interfaces)
    # The validated card and the frozen snapshot keep every declared interface.
    assert len(live.supported_interfaces) == 3
    assert len(frozen.card["supportedInterfaces"]) == 3


def test_projection_reuses_cards_that_already_match():
    snapshot, live = _candidate(lambda card: None)
    assert project_dispatch_interfaces(snapshot, [live])[0] is live


def test_projection_fails_closed_when_the_pinned_interface_is_absent():
    snapshot, _ = _candidate(_add_extra_interfaces)
    payload = deepcopy(snapshot.cards[0].card)
    payload["supportedInterfaces"] = [
        interface for interface in payload["supportedInterfaces"]
        if interface["url"] != snapshot.cards[0].endpoint
    ]
    stranger = ParseDict(payload, AgentCard())
    with pytest.raises(DispatchValidationError) as failure:
        project_dispatch_interfaces(snapshot, [stranger])
    assert failure.value.reason == "CARD_INTERFACE"
    assert failure.value.instance_id == snapshot.cards[0].instance_id


# ---------------------------------------------------------------------------
# Extension four-check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_rejects_extensions_the_card_does_not_declare():
    case = harness()  # plain card declares no extensions at all
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content(extensions={TASK_T_URI}))
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "EXTENSION_UNKNOWN_ACTIVATED"
    assert error.details["execution_id"] == case.snapshot.execution_id
    assert error.details["task_id"] == case.snapshot.bindings[0].task_id
    assert error.details["instance_id"] == case.snapshot.bindings[0].instance_id
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_dispatch_rejects_declared_but_unsupported_extensions():
    case = harness(lambda card: card.update(
        capabilities={"extensions": [{"uri": "urn:legacy"}]}))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content(extensions={"urn:legacy"}))
    assert failure.value.details["reason"] == "EXTENSION_UNSUPPORTED"
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_dispatch_rejects_required_extension_that_is_not_activated():
    case = harness(task_t_card)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    assert failure.value.details["reason"] == "EXTENSION_NOT_ACTIVATED"
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_dispatch_rejects_required_extension_outside_the_support_set():
    # The v4 gap: declared on the card, activated in the message, but the
    # URI is not in the host support set (all three v3 checks would pass).
    case = harness(unknown_required_card)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request,
                                    content(extensions={"urn:unknown-required"}))
    assert failure.value.details["reason"] == "EXTENSION_UNSUPPORTED"
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_dispatch_rejects_task_t_without_metadata_payload():
    case = harness(task_t_card)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content(extensions={TASK_T_URI}))
    assert failure.value.details["reason"] == "EXTENSION_PAYLOAD_MISSING"
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_dispatch_accepts_a_complete_task_t_activation():
    case = harness(task_t_card)
    message = content(extensions={TASK_T_URI}, metadata={TASK_T_URI: {"task": "payload"}})
    result = await case.wrapper.dispatch(case.request, message)
    assert case.inner.dispatched == [(case.request, message)]
    assert result.sentinel == "dispatch-result"
    assert SUPPORTED_EXTENSIONS == {TASK_T_URI, NEGOTIATION_T_URI}


@pytest.mark.asyncio
async def test_dispatch_accepts_negotiation_t_activation_on_a_reply():
    # Negotiation-T is the SDK's native information-exchange round trip:
    # negotiation agents answer a Task-T request with an INPUT_REQUIRED
    # PROPOSE and expect a REPLY, so the four-check must not reject it.
    # Real negotiation cards declare both URIs (Task-T for prompts,
    # Negotiation-T for the exchange), like the SPN sample cards.
    case = harness(lambda card: card.update(capabilities={"extensions": [
        {"uri": TASK_T_URI}, {"uri": NEGOTIATION_T_URI}]}))
    message = content(extensions={NEGOTIATION_T_URI}, metadata={NEGOTIATION_T_URI: {"proposal": "data"}})
    result = await case.wrapper.dispatch(case.request, message)
    assert case.inner.dispatched == [(case.request, message)]
    assert result.sentinel == "dispatch-result"


# ---------------------------------------------------------------------------
# Authentication pre-check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_rejects_authentication_without_credentials_or_provider():
    case = harness(auth_card)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "AUTH_CREDENTIALS_MISSING"
    assert error.details["task_id"] == case.snapshot.bindings[0].task_id
    assert error.details["instance_id"] == case.snapshot.bindings[0].instance_id
    assert not case.inner.dispatched


@pytest.mark.parametrize("entry", [
    {"bearer": {"request_fields": {"user": "u", "secret": "p"}}},
    {"bearer": {"login_url": "http://127.0.0.1:9/login"}},
    {"bearer": {"login_url": "http://127.0.0.1:9/login", "username": "u"}},
    {"other": {"login_url": "http://127.0.0.1:9/login",
               "request_fields": {"user": "u", "secret": "p"}}},
])
@pytest.mark.asyncio
async def test_dispatch_rejects_incomplete_credentials(entry):
    case = harness(auth_card, credentials={"Technical RAN A": entry})
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    assert failure.value.details["reason"] == "AUTH_METHOD_UNSUPPORTED"
    assert not case.inner.dispatched


@pytest.mark.parametrize("entry", [
    COMPLETE_CREDENTIALS,
    {"bearer": {"login_url": "http://127.0.0.1:9/login", "username": "u", "password": "p"}},
    # Optional SDK defaults are never rejection grounds.
    {"bearer": {"login_url": "http://127.0.0.1:9/login",
                "request_fields": {"user": "u", "secret": "p"},
                "token_field": "sessionToken", "method": "PUT"}},
])
@pytest.mark.asyncio
async def test_complete_credentials_pass_the_precheck(entry):
    case = harness(auth_card, credentials={"Technical RAN A": entry})
    await case.wrapper.dispatch(case.request, content())
    assert len(case.inner.dispatched) == 1


@pytest.mark.asyncio
async def test_credentials_satisfying_any_single_requirement_are_accepted():
    # Bearer-or-API-key card, but only the bearer login is configured: the
    # card offers alternatives, so one complete requirement is enough.
    case = harness(alternative_auth_card,
                   credentials={"Technical RAN A": COMPLETE_CREDENTIALS})
    await case.wrapper.dispatch(case.request, content())
    assert len(case.inner.dispatched) == 1


@pytest.mark.asyncio
async def test_a_partially_configured_requirement_is_still_rejected():
    # Bearer-and-API-key card: configuring only the bearer login leaves the
    # single requirement incomplete.
    case = harness(combined_auth_card,
                   credentials={"Technical RAN A": COMPLETE_CREDENTIALS})
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    assert failure.value.details["reason"] == "AUTH_METHOD_UNSUPPORTED"
    assert not case.inner.dispatched


def colliding_group_card(second_header):
    # (key1 AND auxiliary) OR key2 with key1 and auxiliary both writing the
    # same case-insensitive header: a combination whose group adoption
    # depends on runtime token values and is therefore rejected up front.
    def mutate(card):
        card["securitySchemes"] = {
            "key1": {"apiKeySecurityScheme": {"location": "header",
                                              "name": "X-Api-Key"}},
            "auxiliary": {"apiKeySecurityScheme": {"location": "header",
                                                   "name": second_header}},
            "key2": {"apiKeySecurityScheme": {"location": "header",
                                               "name": "x-api-key"}}}
        card["securityRequirements"] = [{"schemes": {"key1": {"list": []},
                                                      "auxiliary": {"list": []}}},
                                         {"schemes": {"key2": {"list": []}}}]
    return mutate


@pytest.mark.parametrize("second_header", ["X-Api-Key", "x-api-key"])
@pytest.mark.asyncio
async def test_dispatch_rejects_schemes_sharing_one_header_within_a_requirement(
        second_header):
    entry = {name: {"login_url": "http://127.0.0.1:9/login",
                    "request_fields": {"user": user, "secret": secret}}
             for name, user, secret in (("key1", "u1", "p1"),
                                        ("auxiliary", "u2", "p2"),
                                        ("key2", "u3", "p3"))}
    case = harness(colliding_group_card(second_header),
                   credentials={"Technical RAN A": entry})
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "AUTH_METHOD_UNSUPPORTED"
    assert error.details["task_id"] == case.snapshot.bindings[0].task_id
    assert error.details["instance_id"] == case.snapshot.bindings[0].instance_id
    assert not case.inner.dispatched


@pytest.mark.asyncio
async def test_a_provider_satisfies_the_mechanism_requirement():
    case = harness(auth_card, provider=Provider())  # presence is enough here
    await case.wrapper.dispatch(case.request, content())
    assert len(case.inner.dispatched) == 1


@pytest.mark.asyncio
async def test_cards_without_authentication_declaration_skip_the_precheck():
    case = harness()
    await case.wrapper.dispatch(case.request, content())
    assert len(case.inner.dispatched) == 1


# ---------------------------------------------------------------------------
# Dispatch exception conversion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_converts_ordinary_exceptions_without_leaking_messages():
    case = harness(inner=FakeEngineClient(RuntimeError("secret token in message")))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details == {
        "reason": "DISPATCH_FAILED",
        "execution_id": case.snapshot.execution_id,
        "task_id": case.snapshot.bindings[0].task_id,
        "instance_id": case.snapshot.bindings[0].instance_id,
        "error_type": "RuntimeError",
    }
    assert "secret token" not in str(error)


@pytest.mark.asyncio
async def test_dispatch_reraises_business_failures_and_cancellation_unchanged():
    original = BusinessFailure("SOME_CODE", "kept", details={"kept": True})
    case = harness(inner=FakeEngineClient(original))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    assert failure.value is original

    cancelled = harness(inner=FakeEngineClient(asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await cancelled.wrapper.dispatch(cancelled.request, content())


@pytest.mark.asyncio
async def test_unmapped_callbacks_report_execution_identity_only():
    case = harness()
    stranger = SimpleNamespace(execution_id="sdk-execution", task_id="never-registered",
                               step_name="explore", agent_name=case.request.agent_name,
                               skill=case.request.skill)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(stranger, content())
    details = failure.value.details
    assert details["reason"] == "DISPATCH_FAILED"
    assert details["execution_id"] == case.snapshot.execution_id
    assert "task_id" not in details
    assert "instance_id" not in details


# ---------------------------------------------------------------------------
# Legacy instance tasks inside role executions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_instance_tasks_inside_role_executions_stay_untouched():
    case = harness()
    workflow = deepcopy(case.workflow)
    workflow["steps"].append({"name": "legacy", "subtasks": [
        {"task_id": "legacy-1", "agent": "Legacy Agent", "skill": "Legacy Skill",
         "description": "Legacy task"},
    ]})
    raw_context = RoleExecutionContext(
        execution_id=case.snapshot.execution_id,
        caller_id=case.snapshot.context.caller_id,
        scope=case.snapshot.context.scope,
        bindings=tuple(case.snapshot.bindings),
    )
    bridge = RoleExecutionBridge(raw_context, workflow)
    bridge.observe({"type": EventType.TASK_REQUEST, "data": {
        "execution_id": "sdk-execution", "task_id": "sdk-role",
        "step": workflow["steps"][0]["name"], "subtask_index": 0,
        "agent": case.request.agent_name,
    }})
    bridge.observe({"type": EventType.TASK_REQUEST, "data": {
        "execution_id": "sdk-execution", "task_id": "sdk-legacy",
        "step": "legacy", "subtask_index": 0, "agent": "Legacy Agent",
    }})
    request = SimpleNamespace(execution_id="sdk-execution", task_id="sdk-legacy",
                              step_name="legacy", agent_name="Legacy Agent",
                              skill="Legacy Skill")
    wrapper = RoleDispatchEngineClient(case.inner, bridge.context, case.snapshot)
    # Content that the four-check would reject is still dispatched untouched.
    await wrapper.dispatch(request, content(extensions={"urn:unknown"}))
    assert len(case.inner.dispatched) == 1
    # Ordinary failures stay unconverted for legacy tasks.
    boom = FakeEngineClient(RuntimeError("legacy failure"))
    strict = RoleDispatchEngineClient(boom, bridge.context, case.snapshot)
    with pytest.raises(RuntimeError):
        await strict.dispatch(request, content())


# ---------------------------------------------------------------------------
# Negotiation reply guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_negotiation_reply_content_runs_the_extension_four_check():
    # The card declares (but does not require) an extension outside the
    # support set; the control point activates it only in its reply.
    case = harness(lambda card: card.update(
        capabilities={"extensions": [{"uri": "urn:negotiation-t"}]}),
        inner=NegotiationClient())
    policy = NegotiationPolicy(content(extensions={"urn:negotiation-t"}))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content(), callbacks=policy)
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "EXTENSION_UNSUPPORTED"
    assert error.details["task_id"] == case.snapshot.bindings[0].task_id
    assert error.details["instance_id"] == case.snapshot.bindings[0].instance_id
    assert policy.negotiations == 1
    # The unsupported reply never became a second outbound request.
    assert case.inner.sent == [frozenset()]


@pytest.mark.asyncio
async def test_negotiation_reply_must_stay_within_the_card_declarations():
    case = harness(inner=NegotiationClient())  # plain card declares no extensions
    policy = NegotiationPolicy(content(extensions={TASK_T_URI}))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content(), callbacks=policy)
    assert failure.value.details["reason"] == "EXTENSION_UNKNOWN_ACTIVATED"
    assert case.inner.sent == [frozenset()]


@pytest.mark.asyncio
async def test_negotiation_reply_with_supported_content_is_forwarded():
    case = harness(task_t_card, inner=NegotiationClient())
    reply = content(extensions={TASK_T_URI}, metadata={TASK_T_URI: {"task": "payload"}})
    policy = NegotiationPolicy(reply)
    message = content(extensions={TASK_T_URI}, metadata={TASK_T_URI: {"task": "first"}})
    result = await case.wrapper.dispatch(case.request, message, callbacks=policy)
    assert result.sentinel == "dispatch-result"
    assert case.inner.sent == [frozenset({TASK_T_URI}), frozenset({TASK_T_URI})]


# ---------------------------------------------------------------------------
# Provider send-time validation
# ---------------------------------------------------------------------------

def test_provider_wrapper_rejects_headers_without_authentication_value():
    provider = Provider(headers={"X-Trace-Id": "trace-1"})
    wrapper = ValidatingAuthProvider(provider, execution_id="execution-x")
    card = ParseDict(bearer_card_dict(), AgentCard())
    with validated_dispatch():
        with pytest.raises(BusinessFailure) as failure:
            wrapper.apply_auth("Technical RAN A", card, {})
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "AUTH_PROVIDER_UNSATISFIED"
    assert error.details["execution_id"] == "execution-x"
    assert "task_id" not in error.details
    assert "instance_id" not in error.details
    assert provider.calls == ["Technical RAN A"]


def test_provider_wrapper_rejects_empty_output_and_exceptions():
    card = ParseDict(bearer_card_dict(), AgentCard())
    empty = ValidatingAuthProvider(Provider(headers={}), execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure) as failure:
            empty.apply_auth("Technical RAN A", card, {})
    assert failure.value.details["reason"] == "AUTH_PROVIDER_UNSATISFIED"

    broken = ValidatingAuthProvider(Provider(exc=RuntimeError("sso exploded")),
                                    execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure) as failure:
            broken.apply_auth("Technical RAN A", card, {})
    error = failure.value
    assert error.details["reason"] == "AUTH_PROVIDER_UNSATISFIED"
    assert error.details["error_type"] == "RuntimeError"
    assert "sso exploded" not in str(error)


@pytest.mark.parametrize("authorization", [
    "", "   ",                       # blank value
    "Bearer", "Bearer   ",           # missing token
    "Basic abc",                     # wrong auth scheme
    "not-a-scheme-token",            # no Bearer prefix at all
])
def test_provider_output_with_malformed_authorization_is_rejected(authorization):
    wrapper = ValidatingAuthProvider(
        Provider(headers={"Authorization": authorization}), execution_id="e")
    card = ParseDict(bearer_card_dict(), AgentCard())
    with validated_dispatch():
        with pytest.raises(BusinessFailure) as failure:
            wrapper.apply_auth("Technical RAN A", card, {})
    assert failure.value.details["reason"] == "AUTH_PROVIDER_UNSATISFIED"


@pytest.mark.parametrize("authorization", ["Bearer token", "bearer token", "BEARER token"])
def test_provider_headers_and_bearer_scheme_compare_case_insensitively(authorization):
    wrapper = ValidatingAuthProvider(
        Provider(headers={"authorization": authorization}), execution_id="e")
    card = ParseDict(bearer_card_dict(), AgentCard())
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", card, headers)
    # The lowercase spelling is accepted and canonicalized to the declared
    # header name, so the SDK's exact-key merge cannot be bypassed.
    assert headers == {"Authorization": authorization}


def test_provider_case_variants_with_equal_values_collapse_into_one_header():
    wrapper = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t", "authorization": "Bearer t"}),
        execution_id="e")
    card = ParseDict(bearer_card_dict(), AgentCard())
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", card, headers)
    assert headers == {"Authorization": "Bearer t"}


def test_provider_case_variants_with_different_values_are_rejected():
    wrapper = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t", "authorization": "Bearer other"}),
        execution_id="e")
    card = ParseDict(bearer_card_dict(), AgentCard())
    with validated_dispatch(agent="Technical RAN A", execution_id="execution-x",
                            task_id="t-1", instance_id="technical-a"):
        with pytest.raises(BusinessFailure) as failure:
            wrapper.apply_auth("Technical RAN A", card, {})
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "AUTH_HEADER_CONFLICT"
    assert error.details["header"] == "authorization"
    assert error.details["execution_id"] == "execution-x"
    assert error.details["task_id"] == "t-1"
    assert error.details["instance_id"] == "technical-a"


def test_provider_output_is_canonicalized_to_the_declared_header_spelling():
    bearer = ValidatingAuthProvider(Provider(headers={"authorization": "Bearer t"}),
                                    execution_id="e")
    headers = {}
    with validated_dispatch():
        bearer.apply_auth("Technical RAN A", ParseDict(bearer_card_dict(), AgentCard()),
                          headers)
    assert headers == {"Authorization": "Bearer t"}

    api_key = ValidatingAuthProvider(Provider(headers={"x-api-key": "secret"}),
                                     execution_id="e")
    headers = {}
    with validated_dispatch():
        api_key.apply_auth("Technical RAN A", ParseDict(api_key_card_dict(), AgentCard()),
                           headers)
    assert headers == {"X-Api-Key": "secret"}


def test_auth_header_configuration_defines_the_effective_contract():
    wrapper = ValidatingAuthProvider(
        Provider(headers={"x-session-auth": "Bearer t"}),
        execution_id="e",
        credentials={"Technical RAN A": {"bearer": {
            "login_url": "https://sso.example/login",
            "request_fields": {"user": "u"}, "token_field": "token",
            "auth_header": "X-Session-Auth", "auth_header_prefix": "Bearer "}}})
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", ParseDict(bearer_card_dict(), AgentCard()),
                           headers)
    # The configured auth_header replaces the Authorization convention, so the
    # provider's case variant aligns with the header the credentials side
    # writes and satisfies the raw-value contract.
    assert headers == {"X-Session-Auth": "Bearer t"}


def test_configured_scheme_spelling_wins_over_later_declarations():
    card = {"name": "Technical RAN A",
            "securitySchemes": {
                "key1": {"apiKeySecurityScheme": {"location": "header",
                                                  "name": "X-Api-Key"}},
                "key2": {"apiKeySecurityScheme": {"location": "header",
                                                  "name": "x-api-key"}}},
            "securityRequirements": [{"schemes": {"key1": {"list": []}}},
                                     {"schemes": {"key2": {"list": []}}}]}
    wrapper = ValidatingAuthProvider(
        Provider(headers={"x-api-key": "secret"}), execution_id="e",
        credentials={"Technical RAN A": {"key1": {
            "login_url": "https://sso.example/login",
            "request_fields": {"user": "u"}, "token_field": "token"}}})
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", ParseDict(card, AgentCard()), headers)
    # Only key1 is configured; its spelling wins over key2's later
    # lowercase declaration, so the provider output dedupes with the
    # credentials header instead of reaching the wire a second time.
    assert headers == {"X-Api-Key": "secret"}

    # Symmetric direction: the later lowercase declaration is the configured
    # one, so its spelling wins over key1's earlier declaration.
    reversed_wrapper = ValidatingAuthProvider(
        Provider(headers={"X-Api-Key": "secret"}), execution_id="e",
        credentials={"Technical RAN A": {"key2": {
            "login_url": "https://sso.example/login",
            "request_fields": {"user": "u"}, "token_field": "token"}}})
    headers = {}
    with validated_dispatch():
        reversed_wrapper.apply_auth("Technical RAN A", ParseDict(card, AgentCard()),
                                    headers)
    assert headers == {"x-api-key": "secret"}


def test_skipped_group_configurations_do_not_win_the_spelling():
    card = {"name": "Technical RAN A",
            "securitySchemes": {
                "key1": {"apiKeySecurityScheme": {"location": "header",
                                                  "name": "X-Api-Key"}},
                "key2": {"apiKeySecurityScheme": {"location": "header",
                                                  "name": "x-api-key"}},
                "auxiliary": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
            # (key1 AND auxiliary) OR key2, with auxiliary unconfigured: the
            # SDK skips the first incomplete group and adopts key2.
            "securityRequirements": [{"schemes": {"auxiliary": {"list": []},
                                                  "key1": {"list": []}}},
                                     {"schemes": {"key2": {"list": []}}}]}
    wrapper = ValidatingAuthProvider(
        Provider(headers={"X-Api-Key": "secret"}), execution_id="e",
        credentials={"Technical RAN A": {
            "key1": {"login_url": "https://sso.example/login",
                     "request_fields": {"user": "u"}, "token_field": "token"},
            "key2": {"login_url": "https://sso.example/login",
                     "request_fields": {"user": "u"}, "token_field": "token"}}})
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", ParseDict(card, AgentCard()), headers)
    # Group 1 is incomplete (auxiliary has no configuration), so the SDK
    # adopts key2 and writes the lowercase declaration: key1's configuration
    # in the skipped group must not impose its spelling.
    assert headers == {"x-api-key": "secret"}


def test_custom_headers_dedupe_case_variants_too():
    wrapper = ValidatingAuthProvider(
        Provider(headers={"X-Custom-Auth": "v", "x-custom-auth": "v"}),
        execution_id="e", custom_headers=("X-Custom-Auth",))
    card = ParseDict({"name": "Technical RAN A"}, AgentCard())
    headers = {}
    with validated_dispatch():
        wrapper.apply_auth("Technical RAN A", card, headers)
    assert headers == {"X-Custom-Auth": "v"}


@pytest.mark.asyncio
async def test_provider_header_conflicts_reject_the_dispatch_with_zero_requests():
    wrapped = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t", "authorization": "Bearer other"}))
    client = ProviderCallingClient(wrapped)
    case = harness(auth_card, provider=Provider(), inner=client)
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    assert failure.value.details["reason"] == "AUTH_HEADER_CONFLICT"
    # The conflict aborts the dispatch before any request is attempted.
    assert not client.dispatched


@pytest.mark.asyncio
async def test_provider_merge_applies_only_inside_the_validated_window():
    wrapped = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t", "authorization": "Bearer t"}))
    client = ProviderCallingClient(wrapped)
    case = harness(inner=client)  # plain card: no authenticated role task
    await case.wrapper.dispatch(case.request, content())
    # Outside the validated window the provider's output stays untouched.
    assert client.auth_headers == [{"Authorization": "Bearer t",
                                    "authorization": "Bearer t"}]
    assert len(client.dispatched) == 1


def test_provider_output_for_api_key_schemes_needs_a_non_empty_value():
    card = ParseDict(api_key_card_dict(), AgentCard())
    blank = ValidatingAuthProvider(Provider(headers={"X-Api-Key": "  "}), execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure):
            blank.apply_auth("Technical RAN A", card, {})
    filled = ValidatingAuthProvider(Provider(headers={"X-Api-Key": "secret"}),
                                    execution_id="e")
    headers = {}
    with validated_dispatch():
        filled.apply_auth("Technical RAN A", card, headers)
    assert headers == {"X-Api-Key": "secret"}


def test_non_header_api_key_locations_fall_back_to_bearer_authorization():
    card = ParseDict(cookie_key_card_dict(), AgentCard())
    wrong = ValidatingAuthProvider(Provider(headers={"X-Api-Key": "secret"}),
                                   execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure):
            wrong.apply_auth("Technical RAN A", card, {})
    right = ValidatingAuthProvider(Provider(headers={"Authorization": "Bearer t"}),
                                   execution_id="e")
    headers = {}
    with validated_dispatch():
        right.apply_auth("Technical RAN A", card, headers)
    assert headers == {"Authorization": "Bearer t"}


def test_scheme_combinations_within_one_requirement_need_every_header():
    card = ParseDict(bearer_key_card_dict(), AgentCard())
    partial = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t"}), execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure):
            partial.apply_auth("Technical RAN A", card, {})
    full = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t", "X-Api-Key": "k"}),
        execution_id="e")
    headers = {}
    with validated_dispatch():
        full.apply_auth("Technical RAN A", card, headers)
    assert headers == {"Authorization": "Bearer t", "X-Api-Key": "k"}


def test_alternative_requirements_accept_either_scheme():
    card = ParseDict(alternative_requirements_card_dict(), AgentCard())
    key_only = ValidatingAuthProvider(Provider(headers={"X-Api-Key": "k"}),
                                      execution_id="e")
    headers = {}
    with validated_dispatch():
        key_only.apply_auth("Technical RAN A", card, headers)
    assert headers == {"X-Api-Key": "k"}
    bearer_only = ValidatingAuthProvider(
        Provider(headers={"Authorization": "Bearer t"}), execution_id="e")
    with validated_dispatch():
        bearer_only.apply_auth("Technical RAN A", card, headers)
    assert headers["Authorization"] == "Bearer t"


def test_provider_wrapper_accepts_scheme_headers_and_custom_conventions():
    bearer = ValidatingAuthProvider(Provider(headers={"Authorization": "Bearer token"}),
                                    execution_id="e")
    headers = {}
    with validated_dispatch():
        bearer.apply_auth("Technical RAN A", ParseDict(bearer_card_dict(), AgentCard()),
                          headers)
    assert headers == {"Authorization": "Bearer token"}

    api_key = ValidatingAuthProvider(Provider(headers={"X-Api-Key": "secret"}),
                                     execution_id="e")
    headers = {}
    with validated_dispatch():
        api_key.apply_auth("Technical RAN A", ParseDict(api_key_card_dict(), AgentCard()),
                           headers)
    assert headers == {"X-Api-Key": "secret"}

    plain_card = ParseDict({"name": "Technical RAN A"}, AgentCard())
    custom = ValidatingAuthProvider(Provider(headers={"X-Custom-Auth": "v"}),
                                    execution_id="e", custom_headers=("X-Custom-Auth",))
    headers = {}
    with validated_dispatch():
        custom.apply_auth("Technical RAN A", plain_card, headers)
    assert headers == {"X-Custom-Auth": "v"}
    # Without the explicit convention the same output is rejected.
    strict = ValidatingAuthProvider(Provider(headers={"X-Custom-Auth": "v"}), execution_id="e")
    with validated_dispatch():
        with pytest.raises(BusinessFailure):
            strict.apply_auth("Technical RAN A", plain_card, {})


@pytest.mark.asyncio
async def test_authless_role_tasks_keep_the_provider_semantics_untouched():
    # The plain card declares no authentication, so even an empty provider
    # output must stay acceptable instead of failing the send.
    wrapped = ValidatingAuthProvider(Provider(headers={}))
    client = ProviderCallingClient(wrapped)
    case = harness(inner=client)
    await case.wrapper.dispatch(case.request, content())
    assert client.auth_headers == [{}]
    assert len(client.dispatched) == 1


@pytest.mark.asyncio
async def test_legacy_dispatches_keep_the_provider_semantics_untouched():
    wrapped = ValidatingAuthProvider(Provider(headers={}))
    client = ProviderCallingClient(wrapped)
    case = harness(inner=client)
    workflow = deepcopy(case.workflow)
    workflow["steps"].append({"name": "legacy", "subtasks": [
        {"task_id": "legacy-1", "agent": "Legacy Agent", "skill": "Legacy Skill",
         "description": "Legacy task"},
    ]})
    raw_context = RoleExecutionContext(
        execution_id=case.snapshot.execution_id,
        caller_id=case.snapshot.context.caller_id,
        scope=case.snapshot.context.scope,
        bindings=tuple(case.snapshot.bindings),
    )
    bridge = RoleExecutionBridge(raw_context, workflow)
    bridge.observe({"type": EventType.TASK_REQUEST, "data": {
        "execution_id": "sdk-execution", "task_id": "sdk-role",
        "step": workflow["steps"][0]["name"], "subtask_index": 0,
        "agent": case.request.agent_name,
    }})
    bridge.observe({"type": EventType.TASK_REQUEST, "data": {
        "execution_id": "sdk-execution", "task_id": "sdk-legacy",
        "step": "legacy", "subtask_index": 0, "agent": "Legacy Agent",
    }})
    legacy_request = SimpleNamespace(execution_id="sdk-execution", task_id="sdk-legacy",
                                     step_name="legacy", agent_name="Legacy Agent",
                                     skill="Legacy Skill")
    wrapper = RoleDispatchEngineClient(client, bridge.context, case.snapshot)
    await wrapper.dispatch(legacy_request, content())
    assert client.auth_headers == [{}]
    assert len(client.dispatched) == 1

    # Provider failures outside the validated scope stay unconverted.
    broken = ProviderCallingClient(Provider(exc=RuntimeError("sso exploded")))
    strict = RoleDispatchEngineClient(broken, bridge.context, case.snapshot)
    with pytest.raises(RuntimeError):
        await strict.dispatch(legacy_request, content())


@pytest.mark.asyncio
async def test_provider_identity_follows_the_dispatch_context():
    class DispatchingClient(FakeEngineClient):
        def __init__(self, provider):
            super().__init__()
            self.provider = provider

        async def dispatch(self, request, content, callbacks=None):
            card = ParseDict(bearer_card_dict(), AgentCard())
            self.provider.apply_auth(request.agent_name, card, {})
            return await super().dispatch(request, content, callbacks)

    provider = Provider(headers={"X-Trace-Id": "trace-1"})
    wrapped = ValidatingAuthProvider(provider, execution_id="not-the-execution-id")
    case = harness(auth_card, provider=Provider(), inner=DispatchingClient(wrapped))
    with pytest.raises(BusinessFailure) as failure:
        await case.wrapper.dispatch(case.request, content())
    error = failure.value
    assert error.code == ROLE_DISPATCH_FAILED
    assert error.details["reason"] == "AUTH_PROVIDER_UNSATISFIED"
    assert error.details["execution_id"] == case.snapshot.execution_id
    assert error.details["task_id"] == case.snapshot.bindings[0].task_id
    assert error.details["instance_id"] == case.snapshot.bindings[0].instance_id
    assert not case.inner.dispatched


# ---------------------------------------------------------------------------
# Runtime wiring
# ---------------------------------------------------------------------------

def dispatch_metadata(snapshot):
    metadata = {
        "__orch_psop_id__": snapshot.template.id,
        "__orch_psop__": snapshot.execution_psop.model_dump_json(),
        **_role_dispatch_metadata(snapshot),
    }
    metadata[PROOF_KEY] = sign_dispatch(metadata, KEY, intent=INTENT)
    return metadata


class PassthroughPolicy(ControlPoint):
    async def on_task(self, request):
        return MessageContent.text(request.instruction)


def capture_engine_client(monkeypatch, captured):
    import host_agent.runtime as runtime
    original = runtime.execute_psop

    async def capture(**kwargs):
        captured.update(kwargs)
        async for event in original(**kwargs):
            yield event

    monkeypatch.setattr(runtime, "execute_psop", capture)


@pytest.mark.asyncio
async def test_role_executions_dispatch_through_the_projected_wrapped_client(monkeypatch):
    snapshot, live = _candidate(_add_extra_interfaces)
    host, queue = executor([live]), Queue()
    stub = StubWorkflowEngineClient()
    host._engine_client_factory.create.return_value = stub
    captured = {}
    capture_engine_client(monkeypatch, captured)

    await host.execute(context(dispatch_metadata(snapshot)), queue)

    args, kwargs = host._engine_client_factory.create.call_args
    projected = args[0]
    assert [interface.url for interface in projected[0].supported_interfaces] == [
        snapshot.cards[0].endpoint]
    assert kwargs.get("auth_provider") is None
    engine_client = captured["engine_client"]
    assert isinstance(engine_client, RoleDispatchEngineClient)
    assert [name for name, _ in stub.sent] == ["Technical RAN A"]
    assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.asyncio
async def test_legacy_executions_bypass_projection_and_wrapping(monkeypatch):
    workflow = {"id": "legacy-template", "name": "Legacy", "steps": [
        {"name": "solo", "subtasks": [
            {"task_id": "t", "agent": "agent_a", "skill": "skill",
             "description": "Legacy task"},
        ]},
    ]}
    host = HostAgentExecutor(
        config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused",
                               role_dispatch_key=KEY),
        control_point_factory=lambda _: PassthroughPolicy(),
        agent_card_provider=SimpleNamespace(
            load=AsyncMock(return_value=[SimpleNamespace(name="agent_a")])),
        engine_client_factory=SimpleNamespace(create=Mock()),
    )
    host._workflow_repository = SimpleNamespace(get=AsyncMock(), find=AsyncMock(return_value=workflow))
    stub = StubWorkflowEngineClient()
    host._engine_client_factory.create.return_value = stub
    captured = {}
    capture_engine_client(monkeypatch, captured)

    queue = Queue()
    await host.execute(context({}), queue)

    args, kwargs = host._engine_client_factory.create.call_args
    assert args[0] and args[0][0].name == "agent_a"
    assert "auth_provider" not in kwargs
    assert captured["engine_client"] is stub
    assert not isinstance(captured["engine_client"], RoleDispatchEngineClient)
    assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.asyncio
async def test_configured_providers_wrap_around_the_transport(monkeypatch):
    snapshot, live = _candidate(lambda card: None)
    user_provider = Provider(headers={"Authorization": "Bearer token"})
    host = HostAgentExecutor(
        config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused",
                               role_dispatch_key=KEY),
        control_point_factory=lambda _: PassthroughPolicy(),
        agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
        engine_client_factory=SimpleNamespace(create=Mock(return_value=StubWorkflowEngineClient())),
        auth_provider=user_provider,
    )
    captured = {}
    capture_engine_client(monkeypatch, captured)

    queue = Queue()
    await host.execute(context(dispatch_metadata(snapshot)), queue)

    args, kwargs = host._engine_client_factory.create.call_args
    assert isinstance(kwargs["auth_provider"], ValidatingAuthProvider)
    assert isinstance(captured["engine_client"], RoleDispatchEngineClient)
    assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
