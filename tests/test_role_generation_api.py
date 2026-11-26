# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from orchestrate.core.catalog_gate import CatalogGate
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.model.psop import PSOP
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.server import external_api, frontend_support_server as server
from tests.role_generation_helpers import JsonModel, catalog_payload, workflow_payload, action_matches, structure_from_prompt


@pytest.fixture
def environment(tmp_path, monkeypatch, account_session):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    monkeypatch.setattr("orchestrate.core.role_generation.configured_catalog_path", lambda: str(path))
    monkeypatch.setattr("orchestrate.server.middleware.async_hit", AsyncMock(return_value=True))
    registry = AsyncMock(side_effect=AssertionError("Role generation must not query instances"))
    monkeypatch.setattr(server, "get_agent_cards", registry)
    monkeypatch.setattr(external_api, "get_agent_cards", registry)
    monkeypatch.setattr(server.solution_package_manager, "link_workflow", Mock())
    storage = WorkflowStorage(str(tmp_path / "store"))
    handler = Mock()
    handler.handle.side_effect = storage.save_psop
    gate = CatalogGate(handler, path_resolver=lambda: str(path))
    monkeypatch.setattr(SharedHandlers, "save_psop", lambda: gate)
    model = JsonModel(workflow_payload())
    monkeypatch.setattr("orchestrate.core.psop_generator.get_llm_instance", lambda: model)
    client = TestClient(server.app, headers=account_session)
    return client, path, model, registry, handler, storage


INTENTS = [
    ("/rest/v1/orchestrate/generate-from-intent", {"user_intent": "Analyze"}, 200),
    ("/api/v1/orchestrate/intent", {"intent": "Analyze"}, 201),
]


@pytest.mark.parametrize("url,body,status", INTENTS)
def test_role_intent_api_uses_no_registry_and_roundtrips_file_storage(environment, url, body, status):
    client, _, _, registry, handler, storage = environment
    response = client.post(url, json={**body, "binding": "role"})
    assert response.status_code == status, response.text
    data = response.json()["data"]
    assert data["catalog_version"] == "generation-v1"
    assert data["steps"][0]["subtasks"][0]["binding"] == "role"
    assert storage.load_psop(data["id"]) == PSOP.model_validate(data)
    registry.assert_not_awaited()
    handler.handle.assert_called_once()


@pytest.mark.parametrize("url,body,status", INTENTS)
def test_catalog_drift_cannot_be_swallowed_by_autosave(environment, url, body, status):
    client, path, model, registry, handler, _ = environment

    def changed_release(_):
        payload = catalog_payload()
        payload["roles"][0]["description"] = "Same IDs, different release"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return workflow_payload()

    model.responses = iter([changed_release])
    response = client.post(url, json={**body, "binding": "role"})
    assert response.status_code == 422
    assert response.json()["message"]["code"] == "CATALOG_VERSION_UNAVAILABLE"
    handler.handle.assert_not_called()
    registry.assert_not_awaited()


@pytest.mark.parametrize("url,body,status", INTENTS)
@pytest.mark.parametrize("version", [None, "missing-version"])
def test_catalog_error_fails_before_model_and_registry(environment, url, body, status, version):
    client, path, model, registry, handler, _ = environment
    if version is None:
        path.unlink()
    response = client.post(url, json={**body, "binding": "role", "catalog_version": version,
                                     "catalog": catalog_payload(), "review_status": "approved"})
    assert response.status_code == 422
    assert response.json()["message"]["code"] == "CATALOG_VERSION_UNAVAILABLE"
    assert model.prompts == []
    registry.assert_not_awaited()
    handler.handle.assert_not_called()


def test_catalog_display_returns_only_exact_approved_projection(environment):
    client, _, model, registry, _, _ = environment
    response = client.get("/rest/v1/orchestrate/role-catalog?catalog_version=generation-v1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["roles"][0]["name"] == "Display role-a"
    assert "source" not in json.dumps(data)
    assert "private-draft" not in json.dumps(data)
    assert client.get("/rest/v1/orchestrate/role-catalog?catalog_version=other").status_code == 422
    assert model.prompts == []
    registry.assert_not_awaited()


@pytest.mark.parametrize("url,body,status", INTENTS)
def test_invalid_mode_options_rejected_before_work(environment, url, body, status):
    client, _, model, registry, handler, _ = environment
    assert client.post(url, json={**body, "binding": "instance", "catalog_version": "v"}).status_code == 422
    assert client.post(url, json={**body, "binding": "bad"}).status_code == 422
    assert model.prompts == []
    handler.handle.assert_not_called()
    registry.assert_not_awaited()


@pytest.mark.parametrize("url,body,status", INTENTS)
def test_model_service_failures_are_not_validation_422(environment, url, body, status):
    client, _, model, _, handler, _ = environment
    model.responses = iter([RuntimeError("private service detail")])
    response = client.post(url, json={**body, "binding": "role"})
    assert response.status_code == 500
    assert "private service detail" not in response.text
    handler.handle.assert_not_called()


def post_preflow(client, route, **options):
    if route == "internal":
        return client.post("/rest/v1/orchestrate/generate-from-preflow", json={
            "preflow": {"name": "Input", "steps_md": "Analyze twice"},
            "agent_cards": [{"deliberately_not_an_agent_card": True}], **options,
        })
    if route == "json":
        return client.post("/api/v1/orchestrate/sop", json={"sop_content": "Analyze twice", **options})
    return client.post("/api/v1/orchestrate/sop", files={"file": ("flow.md", b"Analyze twice", "text/markdown")}, data=options)


@pytest.mark.parametrize("route", ["internal", "json", "file"])
def test_preflow_role_endpoints_preserve_repeated_actions_and_no_registry(environment, route):
    client, _, model, registry, handler, storage = environment
    model.responses = iter([["Analyze", "Analyze"], action_matches(), structure_from_prompt])
    response = post_preflow(client, route, binding="role", catalog_version="generation-v1")
    assert response.status_code == (200 if route == "internal" else 201), response.text
    data = response.json()["data"]
    assert [task["agent"] for task in data["steps"][0]["subtasks"]] == ["role-a", "role-b"]
    assert storage.load_psop(data["id"]) == PSOP.model_validate(data)
    handler.handle.assert_called_once()
    registry.assert_not_awaited()


@pytest.mark.parametrize("route", ["internal", "json", "file"])
def test_preflow_directory_failure_precedes_all_model_calls(environment, route):
    client, path, model, registry, handler, _ = environment
    path.write_text(json.dumps({"catalog_version": "generation-v1", "roles": []}), encoding="utf-8")
    response = post_preflow(client, route, binding="role")
    assert response.status_code == 422
    assert response.json()["message"]["code"] == "NO_APPROVED_ROLE_SKILL"
    assert model.prompts == []
    handler.handle.assert_not_called()
    registry.assert_not_awaited()


@pytest.mark.parametrize("route", ["internal", "json", "file"])
def test_preflow_conflicting_mode_options_are_422(environment, route):
    client, _, model, registry, handler, _ = environment
    assert post_preflow(client, route, binding="instance", catalog_version="v1").status_code == 422
    assert post_preflow(client, route, binding="unknown").status_code == 422
    assert model.prompts == []
    handler.handle.assert_not_called()
    registry.assert_not_awaited()


@pytest.mark.parametrize("route", ["internal", "json", "file"])
def test_preflow_catalog_change_after_structure_generation_is_rejected(environment, route):
    client, path, model, _, handler, _ = environment

    def drift(prompt):
        payload = catalog_payload()
        payload["roles"][1]["description"] = "Changed after matching"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return structure_from_prompt(prompt)

    model.responses = iter([["Analyze", "Analyze"], action_matches(), drift])
    response = post_preflow(client, route, binding="role")
    assert response.status_code == 422
    assert response.json()["message"]["code"] == "CATALOG_VERSION_UNAVAILABLE"
    handler.handle.assert_not_called()


def test_internal_role_preflow_accepts_absent_agent_cards(environment):
    client, _, model, registry, _, _ = environment
    model.responses = iter([["Analyze", "Analyze"], action_matches(), structure_from_prompt])
    response = client.post("/rest/v1/orchestrate/generate-from-preflow", json={
        "preflow": {"name": "Input", "steps_md": "Analyze"}, "binding": "role",
    })
    assert response.status_code == 200, response.text
    registry.assert_not_awaited()


def test_internal_preflow_links_workflow_under_its_binding_slot(environment):
    """The package link must record the generation binding so role and
    instance workflows of one package do not overwrite each other."""
    client, _, model, registry, handler, _ = environment
    model.responses = iter([["Analyze", "Analyze"], action_matches(), structure_from_prompt])
    response = post_preflow(client, "internal", binding="role", catalog_version="generation-v1")
    assert response.status_code == 200, response.text
    server.solution_package_manager.link_workflow.assert_called_once_with(
        "Input", response.json()["data"]["id"], "role")


def test_read_only_catalog_requires_existing_account_authentication(environment):
    response = TestClient(server.app).get("/rest/v1/orchestrate/role-catalog")
    assert response.status_code == 401


def test_read_only_catalog_is_rate_limited_before_loading(environment, monkeypatch):
    client, path, model, _, _, _ = environment
    path.unlink()
    monkeypatch.setattr("orchestrate.server.middleware.async_hit", AsyncMock(return_value=False))
    assert client.get("/rest/v1/orchestrate/role-catalog").status_code == 429
    assert model.prompts == []
