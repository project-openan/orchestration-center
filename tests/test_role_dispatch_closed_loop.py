# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Seventh batch unit B: real closed loops for the expanded candidates.

One mixed role execution dispatches through real A2A transports to an
authenticated worker (login exchange + Bearer header), a required Task-T
extension worker (activated URI, metadata payload, A2A-Extensions header)
and a multi-interface worker whose registry-pinned endpoint must receive
every request while the higher-protocol sibling receives none.

The center-chain tests then drive the same candidates through the real
orchestration-center path — catalog/registry files, live projection,
dispatch SSE, execution records — with a legacy instance task mixed in,
and assert the authentication rejection surfaces with the original task
identity before any business request leaves the host.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from a2a.server.agent_execution import AgentExecutor
from a2a.types import AgentCard, Artifact, Part, Task, TaskState, TaskStatus
from fastapi import Request
from google.protobuf.json_format import MessageToDict, ParseDict
from starlette.responses import JSONResponse
from workflow_engine import ControlPoint, MessageContent

from host_agent.config import HostAgentConfig
from host_agent.role_dispatch import TASK_T_URI
from host_agent.runtime import HostAgentExecutor
from host_agent.service import create_agent_app
from orchestrate.core.model.card_snapshot import freeze_agent_card
from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.core.model.instance_binding import (
    InstanceRegistry, ObservedInstance, ResolutionContext, ResolutionPolicy,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.model.role_execution_snapshot import (
    RoleExecutionSnapshot, freeze_role_execution,
)
from orchestrate.runtime.instance_projection import ResolutionRequest
from orchestrate.runtime.role_resolver import resolve_role_bindings
from orchestrate.server.sse_executor import dispatch_intent_sse
from samples.role_pilot.technical_server import pilot_card
from test_host_role_snapshot import INTENT, KEY, Queue, context, envelope, serving

TOKEN = "synthetic-expanded-session"
SOURCE = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])


def base_card(name, port, instance_skill, execution_skill):
    return {
        "name": name, "version": "1.0.0",
        "description": "Synthetic expanded-candidate fixture; no business certification",
        "supportedInterfaces": [
            {"url": f"http://127.0.0.1:{port}", "protocolBinding": "HTTP+JSON",
             "protocolVersion": "1.0"},
        ],
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
        "skills": [{"id": instance_skill, "name": execution_skill,
                    "description": "Echo only", "tags": ["technical-test"]}],
    }


def auth_card(name, port, instance_skill, execution_skill):
    card = base_card(name, port, instance_skill, execution_skill)
    card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
    return card


def case_variant_key_card(name, port, instance_skill, execution_skill):
    """Two alternative API-key schemes whose header names differ only by case."""
    card = base_card(name, port, instance_skill, execution_skill)
    card["securitySchemes"] = {
        "key1": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}},
        "key2": {"apiKeySecurityScheme": {"location": "header", "name": "x-api-key"}}}
    card["securityRequirements"] = [{"schemes": {"key1": {"list": []}}},
                                     {"schemes": {"key2": {"list": []}}}]
    return card


def partial_group_key_card(name, port, instance_skill, execution_skill):
    """An incomplete AND group in front of a configured alternative.

    (key1 AND auxiliary) OR key2 with auxiliary unconfigured: the SDK
    skips the first group at unconfigured auxiliary and adopts key2,
    whose declaration spells the header lowercase. Protobuf map order
    determines whether key1 logs in before auxiliary is encountered.
    """
    card = base_card(name, port, instance_skill, execution_skill)
    card["securitySchemes"] = {
        "key1": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}},
        "key2": {"apiKeySecurityScheme": {"location": "header", "name": "x-api-key"}},
        "auxiliary": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": {"auxiliary": {"list": []},
                                                  "key1": {"list": []}}},
                                     {"schemes": {"key2": {"list": []}}}]
    return card


def colliding_group_key_card(name, port, instance_skill, execution_skill):
    """Both members of the first AND group authenticate through one header.

    (key1 AND auxiliary) OR key2, everything configured, key1 and
    auxiliary both writing X-Api-Key: whether the SDK adopts that group
    depends on the runtime token values, so the host rejects the
    combination structurally.
    """
    card = base_card(name, port, instance_skill, execution_skill)
    card["securitySchemes"] = {
        "key1": {"apiKeySecurityScheme": {"location": "header", "name": "X-Api-Key"}},
        "key2": {"apiKeySecurityScheme": {"location": "header", "name": "x-api-key"}},
        "auxiliary": {"apiKeySecurityScheme": {"location": "header",
                                                "name": "X-Api-Key"}}}
    card["securityRequirements"] = [{"schemes": {"key1": {"list": []},
                                                  "auxiliary": {"list": []}}},
                                     {"schemes": {"key2": {"list": []}}}]
    return card


def task_t_card(name, port, instance_skill, execution_skill):
    card = base_card(name, port, instance_skill, execution_skill)
    card["capabilities"] = {"streaming": False,
                            "extensions": [{"uri": TASK_T_URI, "required": True}]}
    return card


def multi_interface_card(other_port):
    def build(name, port, instance_skill, execution_skill):
        card = base_card(name, port, instance_skill, execution_skill)
        # The exact-1.0 sibling wins ClientFactory._find_best_interface even
        # against a leading >1.0 entry; without host projection every request
        # would reach the wrong endpoint.
        card["supportedInterfaces"] = [
            {"url": f"http://127.0.0.1:{port}", "protocolBinding": "HTTP+JSON",
             "protocolVersion": "1.1"},
            {"url": f"http://127.0.0.1:{other_port}", "protocolBinding": "HTTP+JSON",
             "protocolVersion": "1.0"},
            {"url": f"http://127.0.0.1:{other_port + 1}", "protocolBinding": "GRPC"},
        ]
        return card
    return build


class EchoExecutor(AgentExecutor):
    def __init__(self):
        self.inputs = []
        self.metadata_keys = []

    async def execute(self, context, event_queue):
        self.inputs.append(context.get_user_input())
        message = getattr(context, "message", None)
        metadata = getattr(message, "metadata", None)
        self.metadata_keys.append(sorted(metadata.keys()) if metadata else [])
        await event_queue.enqueue_event(Task(
            id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[Artifact(artifact_id=str(uuid4()),
                                parts=[Part(text=json.dumps({"technical_only": True}))])],
        ))

    async def cancel(self, context, event_queue):
        await event_queue.enqueue_event(Task(
            id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED)))


class ExpandedPolicy(ControlPoint):
    """Activate Task-T for the extension worker; plain content elsewhere."""

    def __init__(self, execution):
        self.execution = execution

    async def on_task(self, request):
        if self.execution is not None:
            binding = self.execution.binding_for(request)
            assert binding is not None
            assert (binding.agent, binding.execution_skill) == (request.agent_name, request.skill)
        if request.agent_name == "Technical TaskT":
            base = MessageContent.text(json.dumps({"task": "task-t"}))
            return MessageContent(parts=base.parts,
                                  metadata={TASK_T_URI: "expanded-payload"},
                                  extensions={TASK_T_URI})
        return MessageContent.text(json.dumps({"task": "plain"}))


def expanded_snapshot(port_auth, port_taskt, port_multi, port_other):
    source = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])
    workers = [
        ("auth", "Technical Auth", auth_card, ("explore-auth", "auth-1", "Explore Auth")),
        ("taskt", "Technical TaskT", task_t_card, ("explore-taskt", "taskt-1", "Explore TaskT")),
        ("multi", "Technical Multi", multi_interface_card(port_other),
         ("explore-multi", "multi-1", "Explore Multi")),
    ]
    ports = {"auth": port_auth, "taskt": port_taskt, "multi": port_multi}
    catalog = RoleCatalog.model_validate(dict(
        catalog_version="synthetic-v1",
        roles=[dict(role_id="test-optimizer", role_version="1", name="Test",
                    description="Synthetic only", source=source, review_status="approved",
                    skills=[dict(skill_id=worker[3][0], name=f"Explore {worker[0]}",
                                 description="Expanded candidate echo", source=source,
                                 review_status="approved")
                            for worker in workers])]))
    template = PSOP.model_validate(dict(
        id="expanded-template", name="Expanded", catalog_version="synthetic-v1",
        steps=[dict(name="expanded", subtasks=[
            dict(task_id=f"t-{worker[0]}", description="Echo", binding="role",
                 agent="test-optimizer", skill=worker[3][0], role_version="1")
            for worker in workers])]))
    scope = {"tenant": "technical-demo", "site": "city-a", "business_object": "ran-a"}
    instances, observed, cards, live_cards = [], [], [], []
    for key, name, builder, (skill_id, instance_skill, execution_skill) in workers:
        card = builder(name, ports[key], instance_skill, execution_skill)
        live = ParseDict(card, AgentCard())
        canonical = MessageToDict(live)
        endpoint = canonical["supportedInterfaces"][0]["url"]
        instances.append(dict(
            instance_id=f"technical-{key}", agent_name=name, endpoint=endpoint,
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[dict(role_id="test-optimizer", role_version="1", skill_id=skill_id,
                         instance_skill_id=instance_skill,
                         execution_skill=execution_skill)]))
        observed.append(ObservedInstance(
            instance_id=f"technical-{key}", agent_name=name, endpoint=endpoint,
            skills={instance_skill: execution_skill}, prerequisites_passed=True))
        cards.append(freeze_agent_card(f"technical-{key}", name, endpoint, canonical))
        live_cards.append(live)
    result = resolve_role_bindings(
        template, catalog,
        InstanceRegistry(config_version="expanded-v1", instances=instances),
        observed,
        ResolutionContext(caller_id="test", scope=scope,
                          authorized_instance_ids={f"technical-{w[0]}" for w in workers}),
        ResolutionPolicy(policy_version="expanded-v1"),
    )
    assert len(result.bindings) == 3
    return freeze_role_execution(template, result, cards, "execution-expanded", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"), live_cards


@pytest.mark.asyncio
async def test_expanded_candidates_complete_a_real_authenticated_extension_pinned_loop():
    login_calls, auth_headers, extension_headers = [], [], []
    pinned_hits, other_hits = [], []
    executors = {"auth": EchoExecutor(), "taskt": EchoExecutor(), "multi": EchoExecutor()}
    token = TOKEN

    def auth_app(port):
        app = create_agent_app(ParseDict(auth_card("Technical Auth", port, "auth-1", "Explore Auth"),
                                         AgentCard()), executors["auth"])

        @app.post("/login")
        async def login(request: Request):
            login_calls.append(await request.json())
            return {"accessSession": token}

        @app.middleware("http")
        async def check_bearer(request, call_next):
            if request.url.path.startswith("/message"):
                auth_headers.append(request.headers.get("Authorization"))
                if auth_headers[-1] != f"Bearer {token}":
                    return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            return await call_next(request)

        return app

    def taskt_app(port):
        app = create_agent_app(ParseDict(task_t_card("Technical TaskT", port, "taskt-1",
                                                     "Explore TaskT"), AgentCard()),
                               executors["taskt"])

        @app.middleware("http")
        async def check_extensions(request, call_next):
            if request.url.path.startswith("/message"):
                value = request.headers.get("A2A-Extensions", "")
                extension_headers.append(value)
                if TASK_T_URI not in value:
                    return JSONResponse(status_code=401, content={"error": "Missing extension"})
            return await call_next(request)

        return app

    def multi_app(hits):
        def build(port):
            app = create_agent_app(ParseDict(base_card("Technical Multi", port, "multi-1",
                                                       "Explore Multi"), AgentCard()),
                                   executors["multi"])

            @app.middleware("http")
            async def count(request, call_next):
                if request.url.path.startswith("/message"):
                    hits.append(request.url.path)
                return await call_next(request)

            return app
        return build

    with serving(auth_app) as port_auth, serving(taskt_app) as port_taskt, \
            serving(multi_app(pinned_hits)) as port_multi, \
            serving(multi_app(other_hits)) as port_other:
        snapshot, live_cards = expanded_snapshot(port_auth, port_taskt, port_multi, port_other)
        _, metadata = envelope(snapshot)
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused", registry_url="http://unused",
                                   role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=live_cards)),
            credentials_config={"Technical Auth": {"bearer": {
                "login_url": f"http://127.0.0.1:{port_auth}/login",
                "request_fields": {"fixture": "expanded-login"},
                "token_field": "accessSession"}}},
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        # Authenticated candidate: one real login, every business request signed.
        assert login_calls == [{"fixture": "expanded-login"}]
        assert auth_headers and all(value == f"Bearer {token}" for value in auth_headers)
        # Required Task-T extension: header carried the URI, metadata the payload.
        assert extension_headers and all(TASK_T_URI in value for value in extension_headers)
        assert any(TASK_T_URI in keys for keys in executors["taskt"].metadata_keys)
        # Multi-interface candidate: pinned endpoint only, sibling stays at zero.
        assert pinned_hits and not other_hits
        assert all(len(executor.inputs) == 1 for executor in executors.values())


# ---------------------------------------------------------------------------
# Provider header merge closed loops (case-insensitive semantics)
# ---------------------------------------------------------------------------

class HeaderProvider:
    """AuthProvider double writing fixed headers."""

    def __init__(self, headers):
        self.headers = dict(headers)
        self.calls = []

    def apply_auth(self, agent_name, agent_card, headers):
        self.calls.append(agent_name)
        headers.update(self.headers)


def auth_only_snapshot(port_auth, card_builder=auth_card):
    """One role task bound to a single authenticated worker."""
    card = card_builder("Technical Auth", port_auth, "auth-1", "Explore Auth")
    live = ParseDict(card, AgentCard())
    canonical = MessageToDict(live)
    endpoint = canonical["supportedInterfaces"][0]["url"]
    scope = {"tenant": "technical-demo", "site": "city-a", "business_object": "ran-a"}
    catalog = RoleCatalog.model_validate(dict(
        catalog_version="synthetic-v1",
        roles=[dict(role_id="test-optimizer", role_version="1", name="Test",
                    description="Synthetic only", source=SOURCE,
                    review_status="approved",
                    skills=[dict(skill_id="explore-auth", name="Explore Auth",
                                 description="Echo", source=SOURCE,
                                 review_status="approved")])]))
    template = PSOP.model_validate(dict(
        id="auth-template", name="Auth", catalog_version="synthetic-v1",
        steps=[dict(name="auth", subtasks=[
            dict(task_id="t-auth", description="Echo", binding="role",
                 agent="test-optimizer", skill="explore-auth", role_version="1")])]))
    result = resolve_role_bindings(
        template, catalog,
        InstanceRegistry(config_version="auth-v1", instances=[dict(
            instance_id="technical-auth", agent_name="Technical Auth", endpoint=endpoint,
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[dict(role_id="test-optimizer", role_version="1", skill_id="explore-auth",
                         instance_skill_id="auth-1", execution_skill="Explore Auth")])]),
        [ObservedInstance(instance_id="technical-auth", agent_name="Technical Auth",
                          endpoint=endpoint, skills={"auth-1": "Explore Auth"},
                          prerequisites_passed=True)],
        ResolutionContext(caller_id="test", scope=scope,
                          authorized_instance_ids={"technical-auth"}),
        ResolutionPolicy(policy_version="auth-v1"),
    )
    assert len(result.bindings) == 1
    cards = [freeze_agent_card("technical-auth", "Technical Auth", endpoint, canonical)]
    return freeze_role_execution(template, result, cards, "execution-auth", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"), live


def watched_auth_app(executor, login_calls, raw_auth_keys, auth_values, token=TOKEN,
                     header_name="Authorization", card_builder=auth_card):
    """Auth worker recording logins and the raw watched-header keys."""
    lowered = header_name.lower().encode()

    def build(port):
        app = create_agent_app(ParseDict(card_builder("Technical Auth", port, "auth-1",
                                                      "Explore Auth"), AgentCard()),
                               executor)

        @app.post("/login")
        async def login(request: Request):
            login_calls.append(await request.json())
            return {"accessSession": token}

        @app.middleware("http")
        async def watch(request, call_next):
            if request.url.path.startswith("/message"):
                raw_auth_keys.extend(key for key, _ in request.headers.raw
                                     if key.lower() == lowered)
                auth_values.append(request.headers.get(header_name))
            return await call_next(request)

        return app
    return build


def task_failure_details(queue):
    """error_code/error_details of the failed task_response, if any."""
    for event in queue.events:
        metadata = getattr(event, "metadata", None)
        if not metadata or "__sdk_event__" not in metadata:
            continue
        event_data = json.loads(metadata["__sdk_event__"])
        if event_data.get("type") == "task_response" and \
                event_data["data"].get("error_code") == "ROLE_DISPATCH_FAILED":
            return event_data["data"]
    return None


@pytest.mark.asyncio
async def test_case_variant_conflicts_reject_the_dispatch_before_any_request():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth)
        _, metadata = envelope(snapshot)
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config={"Technical Auth": {"bearer": {
                "login_url": f"http://127.0.0.1:{port_auth}/login",
                "request_fields": {"fixture": "conflict-login"},
                "token_field": "accessSession"}}},
            auth_provider=HeaderProvider({"authorization": "Bearer different-token"}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
        # The credentials login ran first; the case variant then tripped the
        # SDK's conflict convention, so no business request left the host.
        assert login_calls == [{"fixture": "conflict-login"}]
        assert not raw_auth_keys
        assert not auth_values
        assert not executor.inputs
        failure = task_failure_details(queue)
        assert failure is not None
        assert failure["error_details"]["reason"] == "DISPATCH_FAILED"
        assert failure["error_details"]["error_type"] == "RuntimeError"
        assert failure["error_details"]["task_id"] == "t-auth"
        assert failure["error_details"]["instance_id"] == "technical-auth"


@pytest.mark.asyncio
async def test_lowercase_provider_headers_still_authenticate_the_request():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()
    token = TOKEN

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, token=token)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth)
        _, metadata = envelope(snapshot)
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            auth_provider=HeaderProvider({"authorization": f"Bearer {token}"}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        # Exactly one Authorization header reached the worker (the ASGI
        # server reports header names lowercased); the canonical spelling
        # the wrapper produced is asserted by the unit tests.
        assert raw_auth_keys == [b"authorization"]
        assert auth_values == [f"Bearer {token}"]
        assert len(executor.inputs) == 1
        assert not login_calls


@pytest.mark.asyncio
async def test_matching_case_variant_headers_dedupe_to_one_wire_header():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()
    token = TOKEN

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, token=token)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth)
        _, metadata = envelope(snapshot)
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config={"Technical Auth": {"bearer": {
                "login_url": f"http://127.0.0.1:{port_auth}/login",
                "request_fields": {"fixture": "dedupe-login"},
                "token_field": "accessSession"}}},
            # Same token as the login result, spelled with a lowercase variant.
            auth_provider=HeaderProvider({"authorization": f"Bearer {token}"}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        assert login_calls == [{"fixture": "dedupe-login"}]
        # Credentials and provider agree: one deduplicated header on the wire.
        assert raw_auth_keys == [b"authorization"]
        assert auth_values == [f"Bearer {token}"]
        assert len(executor.inputs) == 1


@pytest.mark.asyncio
async def test_auth_header_configuration_case_variants_merge_case_insensitively():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()
    token = TOKEN

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, token=token,
                                  header_name="X-Session-Auth")) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth)
        _, metadata = envelope(snapshot)
        # The credentials entry relocates the bearer header to X-Session-Auth.
        credentials = {"Technical Auth": {"bearer": {
            "login_url": f"http://127.0.0.1:{port_auth}/login",
            "request_fields": {"fixture": "auth-header-login"},
            "token_field": "accessSession",
            "auth_header": "X-Session-Auth", "auth_header_prefix": "Bearer "}}}
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            # Same value as the credentials side, spelled with a lowercase variant.
            auth_provider=HeaderProvider({"x-session-auth": f"Bearer {token}"}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        assert login_calls == [{"fixture": "auth-header-login"}]
        # Aligned to the configured spelling: exactly one watched header.
        assert raw_auth_keys == [b"x-session-auth"]
        assert auth_values == [f"Bearer {token}"]
        assert len(executor.inputs) == 1

        conflicting = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            auth_provider=HeaderProvider({"x-session-auth": "Bearer other"}),
        )
        queue = Queue()
        await conflicting.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
        # The login ran, the case variant then tripped the SDK's conflict
        # convention at the configured header: no new business request.
        assert login_calls == [{"fixture": "auth-header-login"}] * 2
        assert raw_auth_keys == [b"x-session-auth"]
        assert auth_values == [f"Bearer {token}"]
        assert len(executor.inputs) == 1
        failure = task_failure_details(queue)
        assert failure is not None
        assert failure["error_details"]["reason"] == "DISPATCH_FAILED"
        assert failure["error_details"]["error_type"] == "RuntimeError"
        assert failure["error_details"]["task_id"] == "t-auth"
        assert failure["error_details"]["instance_id"] == "technical-auth"


@pytest.mark.asyncio
async def test_configured_scheme_spelling_wins_over_case_variant_declarations():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()
    token = TOKEN

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, token=token,
                                  header_name="X-Api-Key",
                                  card_builder=case_variant_key_card)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth,
                                            card_builder=case_variant_key_card)
        _, metadata = envelope(snapshot)
        # Only key1 (declared X-Api-Key) carries a credentials configuration.
        credentials = {"Technical Auth": {"key1": {
            "login_url": f"http://127.0.0.1:{port_auth}/login",
            "request_fields": {"fixture": "case-variant-login"},
            "token_field": "accessSession"}}}
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            # key2's declared spelling with the same value the login returned.
            auth_provider=HeaderProvider({"x-api-key": token}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        assert login_calls == [{"fixture": "case-variant-login"}]
        # The configured scheme's spelling won: one deduplicated header.
        assert raw_auth_keys == [b"x-api-key"]
        assert auth_values == [token]
        assert len(executor.inputs) == 1

        conflicting = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            auth_provider=HeaderProvider({"x-api-key": "other-secret"}),
        )
        queue = Queue()
        await conflicting.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
        assert login_calls == [{"fixture": "case-variant-login"}] * 2
        assert raw_auth_keys == [b"x-api-key"]
        assert auth_values == [token]
        assert len(executor.inputs) == 1
        failure = task_failure_details(queue)
        assert failure is not None
        assert failure["error_details"]["reason"] == "DISPATCH_FAILED"
        assert failure["error_details"]["error_type"] == "RuntimeError"
        assert failure["error_details"]["task_id"] == "t-auth"
        assert failure["error_details"]["instance_id"] == "technical-auth"


@pytest.mark.asyncio
async def test_skipped_group_configurations_do_not_affect_the_adopted_scheme():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()
    token = TOKEN
    # A protobuf map has no guaranteed iteration order. The incomplete
    # group may fail at auxiliary before key1 is visited, or after key1
    # logs in. Either way the adopted key2 must log in exactly once.
    allowed_login_sequences = (
        [{"fixture": "key2-login"}],
        [{"fixture": "key1-login"}, {"fixture": "key2-login"}],
    )

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, token=token,
                                  header_name="X-Api-Key",
                                  card_builder=partial_group_key_card)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth,
                                            card_builder=partial_group_key_card)
        _, metadata = envelope(snapshot)
        # Both key1 and key2 are configured; auxiliary is not, so the SDK
        # skips the first incomplete AND group and adopts key2.
        credentials = {"Technical Auth": {
            "key1": {"login_url": f"http://127.0.0.1:{port_auth}/login",
                     "request_fields": {"fixture": "key1-login"},
                     "token_field": "accessSession"},
            "key2": {"login_url": f"http://127.0.0.1:{port_auth}/login",
                     "request_fields": {"fixture": "key2-login"},
                     "token_field": "accessSession"}}}
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            # The skipped group's spelling with the adopted scheme's value.
            auth_provider=HeaderProvider({"X-Api-Key": token}),
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        assert login_calls in allowed_login_sequences
        successful_login_count = len(login_calls)
        # Aligned to the adopted group's lowercase declaration: one header.
        assert raw_auth_keys == [b"x-api-key"]
        assert auth_values == [token]
        assert len(executor.inputs) == 1

        conflicting = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
            auth_provider=HeaderProvider({"x-api-key": "other-secret"}),
        )
        queue = Queue()
        await conflicting.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
        # A new host has its own credentials cache. Check this attempt
        # independently: key1 is still optional, key2 must log in once,
        # and no new business request may leave the host.
        assert login_calls[successful_login_count:] in allowed_login_sequences
        assert raw_auth_keys == [b"x-api-key"]
        assert auth_values == [token]
        assert len(executor.inputs) == 1
        failure = task_failure_details(queue)
        assert failure is not None
        assert failure["error_details"]["reason"] == "DISPATCH_FAILED"
        assert failure["error_details"]["error_type"] == "RuntimeError"
        assert failure["error_details"]["task_id"] == "t-auth"
        assert failure["error_details"]["instance_id"] == "technical-auth"


@pytest.mark.asyncio
async def test_intra_group_header_collisions_reject_the_dispatch_before_any_request():
    login_calls, raw_auth_keys, auth_values = [], [], []
    executor = EchoExecutor()

    with serving(watched_auth_app(executor, login_calls, raw_auth_keys,
                                  auth_values, header_name="X-Api-Key",
                                  card_builder=colliding_group_key_card)) as port_auth:
        snapshot, live = auth_only_snapshot(port_auth,
                                            card_builder=colliding_group_key_card)
        _, metadata = envelope(snapshot)
        # Every scheme carries a complete login; key1 and auxiliary would
        # write the same X-Api-Key header with different tokens, so the
        # SDK's group choice would depend on runtime values.
        credentials = {"Technical Auth": {
            name: {"login_url": f"http://127.0.0.1:{port_auth}/login",
                   "request_fields": {"fixture": f"{name}-login"},
                   "token_field": "accessSession"}
            for name in ("key1", "auxiliary", "key2")}}
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: ExpandedPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
            credentials_config=credentials,
        )
        queue = Queue()
        await host.execute(context(metadata), queue)

        assert queue.events[-1].status.state == TaskState.TASK_STATE_FAILED
        # Rejected structurally at the pre-check: no login, no header on
        # the wire, no business request.
        assert login_calls == []
        assert raw_auth_keys == []
        assert auth_values == []
        assert not executor.inputs
        failure = task_failure_details(queue)
        assert failure is not None
        assert failure["error_details"]["reason"] == "AUTH_METHOD_UNSUPPORTED"
        assert failure["error_details"]["task_id"] == "t-auth"
        assert failure["error_details"]["instance_id"] == "technical-auth"

class CenterPolicy(ControlPoint):
    """Role tasks assert their binding; legacy tasks dispatch plainly."""

    def __init__(self, execution, legacy_agents=frozenset({"Technical Legacy"})):
        self.execution = execution
        self.legacy_agents = legacy_agents

    async def on_task(self, request):
        binding = self.execution.binding_for(request)
        if request.agent_name in self.legacy_agents:
            assert binding is None
        else:
            assert binding is not None
            assert (binding.agent, binding.execution_skill) == (request.agent_name,
                                                                request.skill)
        if request.agent_name == "Technical TaskT":
            base = MessageContent.text(json.dumps({"task": "task-t"}))
            return MessageContent(parts=base.parts,
                                  metadata={TASK_T_URI: "center-payload"},
                                  extensions={TASK_T_URI})
        return MessageContent.text(json.dumps({"task": "plain",
                                               "agent": request.agent_name}))


def center_catalog(tmp_path, skills):
    catalog = RoleCatalog.model_validate(dict(
        catalog_version="synthetic-center-v1",
        roles=[dict(role_id="test-optimizer", role_version="1", name="Test",
                    description="Synthetic only", source=SOURCE,
                    review_status="approved",
                    skills=[dict(skill_id=skill_id, name=f"Explore {name}",
                                 description="Center chain echo", source=SOURCE,
                                 review_status="approved")
                            for skill_id, name in skills])]))
    path = tmp_path / "catalog.json"
    path.write_text(catalog.model_dump_json(), encoding="utf-8")
    return str(path)


def registry_instance(key, name, endpoint, skill_id, instance_skill, execution_skill):
    scope = {"tenant": "technical-demo", "site": "city-a", "business_object": "ran-a"}
    return dict(instance_id=f"technical-{key}", agent_name=name, endpoint=endpoint,
                enabled=True, technical_status="passed", scopes=[scope],
                skills=[dict(role_id="test-optimizer", role_version="1", skill_id=skill_id,
                             instance_skill_id=instance_skill,
                             execution_skill=execution_skill)])


def center_storage(monkeypatch, tmp_path, template):
    """Validate and store the template through the real catalog gate."""
    from orchestrate.core.catalog_gate import CatalogGate
    from orchestrate.core.persistence import WorkflowStorage

    records = []
    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler",
                        lambda _: SimpleNamespace(handle=records.append))
    store = WorkflowStorage(str(tmp_path / "store"))
    CatalogGate(SimpleNamespace(handle=store.save_psop)).handle(template)
    return records, store.load_psop(template.id)


async def collect_events(cards, template, scope="technical-demo/city-a/ran-a"):
    response = await dispatch_intent_sse(cards, INTENT, target_agent="Host Agent",
                                         lang="en", psop=template,
                                         resolution_request=ResolutionRequest(scope=scope))
    return [json.loads(frame.removeprefix("data: ")) async for frame in response.body_iterator
            if frame.startswith("data: ")]


@pytest.mark.asyncio
async def test_center_chain_executes_mixed_role_and_legacy_tasks_end_to_end(
        monkeypatch, tmp_path):
    login_calls, auth_headers, extension_headers = [], [], []
    pinned_hits, other_hits = [], []
    executors = {"auth": EchoExecutor(), "taskt": EchoExecutor(),
                 "multi": EchoExecutor(), "legacy": EchoExecutor()}
    token = TOKEN

    def auth_app(port):
        app = create_agent_app(ParseDict(auth_card("Technical Auth", port, "auth-1",
                                                   "Explore Auth"), AgentCard()),
                               executors["auth"])

        @app.post("/login")
        async def login(request: Request):
            login_calls.append(await request.json())
            return {"accessSession": token}

        @app.middleware("http")
        async def check_bearer(request, call_next):
            if request.url.path.startswith("/message"):
                auth_headers.append(request.headers.get("Authorization"))
                if auth_headers[-1] != f"Bearer {token}":
                    return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            return await call_next(request)

        return app

    def taskt_app(port):
        app = create_agent_app(ParseDict(task_t_card("Technical TaskT", port, "taskt-1",
                                                     "Explore TaskT"), AgentCard()),
                               executors["taskt"])

        @app.middleware("http")
        async def check_extensions(request, call_next):
            if request.url.path.startswith("/message"):
                value = request.headers.get("A2A-Extensions", "")
                extension_headers.append(value)
                if TASK_T_URI not in value:
                    return JSONResponse(status_code=401, content={"error": "Missing extension"})
            return await call_next(request)

        return app

    def multi_app(hits):
        def build(port):
            app = create_agent_app(ParseDict(base_card("Technical Multi", port, "multi-1",
                                                       "Explore Multi"), AgentCard()),
                                   executors["multi"])

            @app.middleware("http")
            async def count(request, call_next):
                if request.url.path.startswith("/message"):
                    hits.append(request.url.path)
                return await call_next(request)

            return app
        return build

    def legacy_app(port):
        return create_agent_app(ParseDict(base_card("Technical Legacy", port, "legacy-1",
                                                    "Explore Legacy"), AgentCard()),
                                executors["legacy"])

    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", KEY)
    with serving(auth_app) as port_auth, serving(taskt_app) as port_taskt, \
            serving(multi_app(pinned_hits)) as port_multi, \
            serving(multi_app(other_hits)) as port_other, \
            serving(legacy_app) as port_legacy:
        live_cards = [
            ParseDict(auth_card("Technical Auth", port_auth, "auth-1", "Explore Auth"),
                      AgentCard()),
            ParseDict(task_t_card("Technical TaskT", port_taskt, "taskt-1", "Explore TaskT"),
                      AgentCard()),
            ParseDict(multi_interface_card(port_other)("Technical Multi", port_multi, "multi-1",
                                                       "Explore Multi"), AgentCard()),
            ParseDict(base_card("Technical Legacy", port_legacy, "legacy-1",
                                "Explore Legacy"), AgentCard()),
        ]
        instances = [
            registry_instance("auth", "Technical Auth",
                              MessageToDict(live_cards[0])["supportedInterfaces"][0]["url"],
                              "explore-auth", "auth-1", "Explore Auth"),
            registry_instance("taskt", "Technical TaskT",
                              MessageToDict(live_cards[1])["supportedInterfaces"][0]["url"],
                              "explore-taskt", "taskt-1", "Explore TaskT"),
            registry_instance("multi", "Technical Multi",
                              MessageToDict(live_cards[2])["supportedInterfaces"][0]["url"],
                              "explore-multi", "multi-1", "Explore Multi"),
        ]
        monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                            lambda: center_catalog(tmp_path, [
                                ("explore-auth", "auth"), ("explore-taskt", "taskt"),
                                ("explore-multi", "multi")]))
        monkeypatch.setattr("orchestrate.core.role_generation.configured_catalog_path",
                            lambda: center_catalog(tmp_path, [
                                ("explore-auth", "auth"), ("explore-taskt", "taskt"),
                                ("explore-multi", "multi")]))
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(InstanceRegistry(
            config_version="center-v1", instances=instances).model_dump_json(),
            encoding="utf-8")
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                            lambda: str(registry_path))
        monkeypatch.setattr("orchestrate.runtime.instance_projection."
                            "configured_authorized_instances",
                            lambda: ["technical-auth", "technical-taskt", "technical-multi"])

        template = PSOP.model_validate(dict(
            id="center-expanded-template", name="Center Expanded",
            catalog_version="synthetic-center-v1",
            steps=[dict(name="expanded", subtasks=[
                dict(task_id="t-auth", description="Echo auth", binding="role",
                     agent="test-optimizer", skill="explore-auth", role_version="1"),
                dict(task_id="t-taskt", description="Echo taskt", binding="role",
                     agent="test-optimizer", skill="explore-taskt", role_version="1"),
                dict(task_id="t-multi", description="Echo multi", binding="role",
                     agent="test-optimizer", skill="explore-multi", role_version="1"),
            ], next=[dict(step="legacy", condition="")]),
                dict(name="legacy", subtasks=[dict(
                    task_id="legacy-1", agent="Technical Legacy", skill="Explore Legacy",
                    description="Legacy instance task")]),
            ]))
        records, template = center_storage(monkeypatch, tmp_path, template)
        original_template = template.model_dump_json()

        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: CenterPolicy(ctx.role_execution),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=live_cards)),
            credentials_config={"Technical Auth": {"bearer": {
                "login_url": f"http://127.0.0.1:{port_auth}/login",
                "request_fields": {"fixture": "center-login"},
                "token_field": "accessSession"}}},
        )

        def host_app(port):
            card = pilot_card("a", port)
            card.name = "Host Agent"
            card.capabilities.streaming = True
            return create_agent_app(card, host)

        with serving(host_app) as port_host:
            target_card = pilot_card("a", port_host)
            target_card.name = "Host Agent"
            target_card.capabilities.streaming = True
            events = await asyncio.wait_for(
                collect_events([target_card, *live_cards], template), timeout=30)

        assert not [event for event in events if event["type"] == "error"], events
        assert any(event["type"] == "complete" for event in events)
        resolution = next(event for event in events if event["type"] == "resolution")
        snapshot = RoleExecutionSnapshot.model_validate(
            resolution["data"]["resolution_snapshot"])
        assert records[-1].execution_id == snapshot.execution_id
        assert records[-1].status == ExecutionStatus.SUCCESS
        assert records[-1].snapshot_fingerprint == snapshot.fingerprint
        # Live projection admitted all three candidates; the frozen evidence
        # keeps every declared interface of the multi-interface card.
        frozen = {card.instance_id: card for card in snapshot.cards}
        assert set(frozen) == {"technical-auth", "technical-taskt", "technical-multi"}
        assert len(frozen["technical-multi"].card["supportedInterfaces"]) == 3
        # Authenticated candidate: one real login, every business request signed.
        assert login_calls == [{"fixture": "center-login"}]
        assert auth_headers and all(value == f"Bearer {token}" for value in auth_headers)
        # Required Task-T extension: header carried the URI, metadata the payload.
        assert extension_headers and all(TASK_T_URI in value for value in extension_headers)
        assert any(TASK_T_URI in keys for keys in executors["taskt"].metadata_keys)
        # Multi-interface candidate: pinned endpoint only, sibling stays at zero.
        assert pinned_hits and not other_hits
        # Legacy instance task: dispatched untouched inside the role execution.
        assert json.loads(executors["legacy"].inputs[0])["agent"] == "Technical Legacy"
        assert all(len(executor.inputs) == 1 for executor in executors.values())
        # The stored template is never mutated by the dispatch.
        assert template.model_dump_json() == original_template


@pytest.mark.asyncio
async def test_center_chain_rejects_role_candidates_without_credentials(
        monkeypatch, tmp_path):
    login_calls, auth_headers = [], []
    worker = EchoExecutor()

    def auth_app(port):
        app = create_agent_app(ParseDict(auth_card("Technical Auth", port, "auth-1",
                                                   "Explore Auth"), AgentCard()), worker)

        @app.post("/login")
        async def login(request: Request):
            login_calls.append(await request.json())
            return {"accessSession": "never-issued"}

        @app.middleware("http")
        async def watch(request, call_next):
            if request.url.path.startswith("/message"):
                auth_headers.append(request.headers.get("Authorization"))
            return await call_next(request)

        return app

    monkeypatch.setenv("ORCH_ROLE_DISPATCH_KEY", KEY)
    with serving(auth_app) as port_auth:
        live = ParseDict(auth_card("Technical Auth", port_auth, "auth-1", "Explore Auth"),
                         AgentCard())
        catalog_path = center_catalog(tmp_path, [("explore-auth", "auth")])
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(InstanceRegistry(config_version="center-v1", instances=[
            registry_instance("auth", "Technical Auth",
                              MessageToDict(live)["supportedInterfaces"][0]["url"],
                              "explore-auth", "auth-1", "Explore Auth"),
        ]).model_dump_json(), encoding="utf-8")
        monkeypatch.setattr("orchestrate.core.catalog_gate.configured_catalog_path",
                            lambda: catalog_path)
        monkeypatch.setattr("orchestrate.core.role_generation.configured_catalog_path",
                            lambda: catalog_path)
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_registry_path",
                            lambda: str(registry_path))
        monkeypatch.setattr("orchestrate.runtime.instance_projection."
                            "configured_authorized_instances",
                            lambda: ["technical-auth"])

        template = PSOP.model_validate(dict(
            id="center-reject-template", name="Center Reject",
            catalog_version="synthetic-center-v1",
            steps=[dict(name="expanded", subtasks=[
                dict(task_id="t-auth", description="Echo auth", binding="role",
                     agent="test-optimizer", skill="explore-auth", role_version="1"),
            ])]))
        records, template = center_storage(monkeypatch, tmp_path, template)

        # No credentials_config and no auth provider: the pre-check must
        # reject the dispatch before any request reaches the worker.
        host = HostAgentExecutor(
            config=HostAgentConfig(orchestration_url="http://unused",
                                   registry_url="http://unused", role_dispatch_key=KEY),
            control_point_factory=lambda ctx: CenterPolicy(ctx.role_execution,
                                                           legacy_agents=frozenset()),
            agent_card_provider=SimpleNamespace(load=AsyncMock(return_value=[live])),
        )

        def host_app(port):
            card = pilot_card("a", port)
            card.name = "Host Agent"
            card.capabilities.streaming = True
            return create_agent_app(card, host)

        with serving(host_app) as port_host:
            target_card = pilot_card("a", port_host)
            target_card.name = "Host Agent"
            target_card.capabilities.streaming = True
            events = await asyncio.wait_for(
                collect_events([target_card, live], template), timeout=30)

        failures = [event["data"] for event in events if event["type"] == "task_response"
                    and event["data"].get("error_code") == "ROLE_DISPATCH_FAILED"]
        assert len(failures) == 1, events
        data = failures[0]
        # The original task identity travels with the rejection.
        assert data["error_details"]["reason"] == "AUTH_CREDENTIALS_MISSING"
        assert data["error_details"]["task_id"] == "t-auth"
        assert data["error_details"]["instance_id"] == "technical-auth"
        assert data["agent"] == "Technical Auth"
        assert any(event["type"] == "error" for event in events)
        record = records[-1]
        assert record.status == ExecutionStatus.FAILED
        assert record.execution_id == data["error_details"]["execution_id"]
        stored = [event for event in record.events if event.get("type") == "task_response"
                  and event["data"].get("error_code") == "ROLE_DISPATCH_FAILED"]
        assert stored
        assert stored[0]["data"]["error_details"]["task_id"] == "t-auth"
        # Zero business requests, zero logins.
        assert not worker.inputs
        assert not login_calls
        assert not auth_headers
