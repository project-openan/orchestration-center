# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import json
import socket
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
import uvicorn
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError

from orchestrate.core.model.card_snapshot import freeze_agent_card
from orchestrate.core.model.instance_binding import InstanceRegistry, ObservedInstance, ResolutionContext, ResolutionPolicy
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.model.role_execution_snapshot import RoleExecutionSnapshot, content_digest, freeze_role_execution
from orchestrate.runtime.role_resolver import resolve_role_bindings
from samples.role_pilot.technical_server import pilot_app, pilot_card


def prepared(port_a=18991, port_b=18992, city="a"):
    source = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])
    catalog = RoleCatalog.model_validate(dict(catalog_version="synthetic-v1", roles=[dict(
        role_id="test-optimizer", role_version="1", name="Test", description="Synthetic only",
        source=source, review_status="approved", skills=[dict(skill_id="explore", name="Explore",
        description="Routing echo only", source=source, review_status="approved")])]))
    template = PSOP.model_validate(dict(id="test-template", name="Test", catalog_version="synthetic-v1",
        steps=[dict(name="explore", subtasks=[dict(task_id="t1", description="Explore", binding="role",
        agent="test-optimizer", skill="explore", role_version="1")])]))
    instances, observed, cards = [], [], []
    for key, port in (("a", port_a), ("b", port_b)):
        card = MessageToDict(pilot_card(key, port))
        endpoint = card["supportedInterfaces"][0]["url"]
        scope = dict(tenant="technical-demo", site=f"city-{key}", business_object=f"ran-{key}")
        instances.append(dict(instance_id=f"technical-{key}", agent_name=card["name"], endpoint=endpoint,
            enabled=True, technical_status="passed", scopes=[scope], skills=[dict(role_id="test-optimizer",
            role_version="1", skill_id="explore", instance_skill_id=f"explore-{key}", execution_skill=f"Explore {key.upper()}")]))
        observed.append(ObservedInstance(instance_id=f"technical-{key}", agent_name=card["name"], endpoint=endpoint,
            skills={f"explore-{key}": f"Explore {key.upper()}"}, prerequisites_passed=True))
        cards.append(freeze_agent_card(f"technical-{key}", card["name"], endpoint, card))
    result = resolve_role_bindings(template, catalog, InstanceRegistry(config_version="test-v1", instances=instances),
        observed, ResolutionContext(caller_id="test", scope=dict(tenant="technical-demo", site=f"city-{city}", business_object=f"ran-{city}"),
        authorized_instance_ids={"technical-a", "technical-b"}), ResolutionPolicy(policy_version="test-v1"))
    selected = [c for c in cards if c.instance_id == result.bindings[0]["instance_id"]]
    return template, result, selected


def test_snapshot_roundtrip_and_input_isolation():
    template, result, cards = prepared()
    snapshot = freeze_role_execution(template, result, cards, "execution-1", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
    wire = snapshot.model_dump_json()
    cards[0].card["name"] = "mutated"
    result.execution_psop.name = "mutated"
    assert snapshot.model_dump_json() == wire
    assert RoleExecutionSnapshot.model_validate_json(wire) == snapshot


def test_authorization_set_order_does_not_change_digest():
    assert content_digest({"context": {"authorized_instance_ids": ["a", "b"]}}) == content_digest(
        {"context": {"authorized_instance_ids": ["b", "a"]}})


@pytest.mark.parametrize("change", ["endpoint", "role", "skill", "graph", "missing_card", "unauthorized"])
def test_snapshot_semantic_tampering_rejected_even_with_new_hash(change):
    payload = freeze_role_execution(*prepared(), "execution-1", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc").model_dump(mode="json")
    if change == "endpoint":
        payload["cards"][0]["endpoint"] = "http://wrong.test"
    elif change == "role":
        payload["bindings"][0]["role_id"] = "other"
    elif change == "skill":
        payload["bindings"][0]["instance_skill_id"] = "unknown"
    elif change == "graph":
        payload["execution_psop"]["steps"][0]["name"] = "changed"
    elif change == "missing_card":
        payload["cards"] = []
    else:
        payload["context"]["authorized_instance_ids"] = []
    payload["fingerprint"] = content_digest({k: v for k, v in payload.items() if k != "fingerprint"})
    with pytest.raises(ValidationError):
        RoleExecutionSnapshot.model_validate(payload)


@contextmanager
def live_server(city):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(pilot_app(city, port), log_level="error", lifespan="off"))
    worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started, "A2A test server did not start"
        yield port
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        assert not worker.is_alive(), "A2A test server did not stop"


def send(endpoint, request):
    response = httpx.post(endpoint + "/message:send", json={"message": {
        "messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": json.dumps(request)}]},
        "configuration": {"returnImmediately": False}}, headers={"A2A-Version": "1.0"}, timeout=10, trust_env=False)
    assert response.status_code == 200, response.text
    return response.json()


def test_two_real_a2a_endpoints_match_resolved_snapshots():
    with live_server("a") as port_a, live_server("b") as port_b:
        for city in ("a", "b"):
            template, result, cards = prepared(port_a, port_b, city)
            before = template.model_dump_json()
            snapshot = freeze_role_execution(template, result, cards, str(uuid4()), catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
            request = {**snapshot.context.scope.model_dump(), "skill_id": snapshot.bindings[0].instance_skill_id}
            response = send(snapshot.cards[0].endpoint, request)
            task = response["task"]
            assert task["status"]["state"] == "TASK_STATE_COMPLETED"
            evidence = json.loads(task["artifacts"][0]["parts"][0]["text"])
            assert evidence["instance_id"] == snapshot.bindings[0].instance_id
            assert evidence["agent_name"] == snapshot.cards[0].agent_name
            assert evidence["technical_only"] is True
            request["site"] = "wrong-city"
            assert send(snapshot.cards[0].endpoint, request)["task"]["status"]["state"] == "TASK_STATE_FAILED"
            assert template.model_dump_json() == before
