# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Installed SDK and real center handlers, with synthetic accounts/storage."""

import hashlib
import os
from types import SimpleNamespace

import httpx
import pytest

from orchestrate.server import account_api, auth, external_api, middleware
from orchestrate.server import frontend_support_server as server
from samples.spn_host_agent import bootstrap


@pytest.fixture(autouse=True)
def center_env(monkeypatch):
    monkeypatch.setattr(bootstrap, "dotenv_values", lambda *args, **kwargs: {})
    for name in list(os.environ):
        if name.startswith("HOST_ORCHESTRATION_"):
            monkeypatch.delenv(name)


@pytest.fixture
def center(monkeypatch):
    password = "LocalPackageTest9!"
    conf = {
        "enable_https": "false",
        "persistence_mode": "file",
        "external.auth.mode": "user",
        "access_password": hashlib.sha256(password.encode()).hexdigest(),
        "access_token_ttl": "60",
    }
    context = SimpleNamespace(has_users=False, mode="file")
    for module in (auth, account_api, server):
        monkeypatch.setattr(module, "get_conf", lambda: conf, raising=False)
        monkeypatch.setattr(module, "current_context", lambda: context)
    store = auth._SessionStore()
    monkeypatch.setattr(auth, "_session_store", store)
    monkeypatch.setattr(auth, "_pending_password_change", set())
    monkeypatch.setattr(
        middleware, "limiter", middleware.strategies.MovingWindowRateLimiter(middleware.storage.MemoryStorage())
    )
    workflow = {"id": "package-test", "name": "Package integration", "steps": []}
    retrieval = SimpleNamespace(
        get_psop_by_id=lambda _: SimpleNamespace(model_dump=lambda: workflow),
        retrieve_psop_by_intent_topn=lambda *_: [
            SimpleNamespace(
                to_dict=lambda: {
                    "workflow_id": workflow["id"],
                    "workflow_type": "psop",
                    "name": workflow["name"],
                }
            )
        ],
    )
    monkeypatch.setattr(external_api.SharedHandlers, "retrieval", lambda: retrieval)
    requests = []

    class RecordedASGI(httpx.ASGITransport):
        async def handle_async_request(self, request):
            response = await super().handle_async_request(request)
            requests.append((request.method, request.url.path, response.status_code))
            return response

    transport = RecordedASGI(app=server.app)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    return password, store, requests


@pytest.mark.asyncio
async def test_composed_host_repository_searches_loads_and_renews(center, monkeypatch):
    password, store, requests = center
    monkeypatch.setenv("HOST_ORCHESTRATION_USERNAME", "admin")
    monkeypatch.setenv("HOST_ORCHESTRATION_PASSWORD", password)
    repository = bootstrap.create_workflow_repository("https://sdk-center.test", ssl_verify=True)
    assert requests == []  # Composition must not log in until a lookup is needed.
    assert (await repository.find("synthetic intent")).id == "package-test"
    assert sum(path == "/api/v1/auth/token" for _, path, _ in requests) == 1
    store.revoke_user("admin")
    assert (await repository.get("package-test")).id == "package-test"
    assert sum(path == "/api/v1/auth/token" for _, path, _ in requests) == 2
    assert sum(status == 401 for _, _, status in requests) == 1


@pytest.mark.asyncio
async def test_composed_host_repository_accepts_an_explicit_bearer(center, monkeypatch):
    _, store, requests = center
    token, _ = store.create("admin", "admin")
    monkeypatch.setenv("HOST_ORCHESTRATION_TOKEN", token)
    repository = bootstrap.create_workflow_repository("https://sdk-center.test", ssl_verify=True)
    assert (await repository.find("synthetic intent")).id == "package-test"
    assert not any(path == "/api/v1/auth/token" for _, path, _ in requests)


@pytest.mark.asyncio
async def test_no_credentials_cannot_bypass_center_authentication(center):
    repository = bootstrap.create_workflow_repository("https://sdk-center.test", ssl_verify=True)
    with pytest.raises(httpx.HTTPStatusError) as error:
        await repository.get("package-test")
    assert error.value.response.status_code == 401


@pytest.mark.parametrize(
    "variables",
    [
        {"HOST_ORCHESTRATION_USERNAME": "admin"},
        {"HOST_ORCHESTRATION_PASSWORD": "synthetic-password"},
        {
            "HOST_ORCHESTRATION_USERNAME": "admin",
            "HOST_ORCHESTRATION_PASSWORD": "synthetic-password",
            "HOST_ORCHESTRATION_TOKEN": "synthetic-token",
        },
    ],
)
def test_incomplete_or_conflicting_credentials_fail_during_composition(monkeypatch, variables):
    for key, value in variables.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as error:
        bootstrap.create_workflow_repository("https://sdk-center.test", ssl_verify=True)
    assert "synthetic-password" not in str(error.value)
    assert "synthetic-token" not in str(error.value)


def test_sample_executor_receives_the_configured_repository(monkeypatch):
    monkeypatch.setenv("HOST_ORCHESTRATION_URL", "https://center.test/deployment")
    repository = object()
    seen = {}

    def create_repository(url, *, ssl_verify, environment):
        seen.update(url=url, ssl_verify=ssl_verify)
        assert environment["HOST_ORCHESTRATION_URL"] == url
        return repository

    monkeypatch.setattr(bootstrap, "get_conf", lambda: {"client_verify_server": "true"})
    monkeypatch.setattr(bootstrap, "create_workflow_repository", create_repository)
    monkeypatch.setattr(bootstrap, "SpnExtensionLifecycle", lambda *args: None)
    monkeypatch.setattr(bootstrap, "HostAgentExecutor", lambda **kwargs: kwargs)
    executor = bootstrap.create_spn_host_executor()
    assert executor["workflow_repository"] is repository
    assert executor["config"].orchestration_url == seen["url"] == "https://center.test/deployment"
    assert seen["ssl_verify"] is True


def test_sample_forwards_center_tls_identity(monkeypatch):
    captured = {}
    monkeypatch.setenv("HOST_ORCHESTRATION_CA_FILE", "ca.pem")
    monkeypatch.setenv("HOST_ORCHESTRATION_CLIENT_CERT", "client.pem")
    monkeypatch.setenv("HOST_ORCHESTRATION_CLIENT_KEY", "key.pem")
    monkeypatch.setenv("HOST_ORCHESTRATION_CLIENT_KEY_PASSWORD", "synthetic-key-password")
    monkeypatch.setenv("HOST_ORCHESTRATION_CRL_FILE", "revoked.pem")
    monkeypatch.setattr(bootstrap, "OrchestrationWorkflowRepository", lambda **kwargs: captured.update(kwargs))
    bootstrap.create_workflow_repository("https://center.test", ssl_verify=True)
    assert captured == dict(
        orch_url="https://center.test",
        ssl_verify=True,
        auth_provider=None,
        ca_certs_path="ca.pem",
        client_cert_path="client.pem",
        client_key_path="key.pem",
        client_key_password="synthetic-key-password",
        crl_path="revoked.pem",
    )


def test_dotenv_settings_are_available_without_overriding_process_secrets(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        bootstrap,
        "dotenv_values",
        lambda *args, **kwargs: {
            "HOST_ORCHESTRATION_USERNAME": "file-user",
            "HOST_ORCHESTRATION_PASSWORD": "file-password",
            "HOST_ORCHESTRATION_CA_FILE": "file-ca.pem",
        },
    )
    monkeypatch.setenv("HOST_ORCHESTRATION_PASSWORD", "process-password")
    provider = object()

    def create_auth(url, username, password):
        captured.update(url=url, username=username, password=password)
        return provider

    monkeypatch.setattr(bootstrap, "OrchestrationAccountAuth", create_auth)
    repository = bootstrap.create_workflow_repository("https://center.test", ssl_verify=True)
    assert captured == dict(url="https://center.test", username="file-user", password="process-password")
    assert repository._request_options["auth_provider"] is provider
    assert repository._request_options["ca_certs_path"] == "file-ca.pem"
