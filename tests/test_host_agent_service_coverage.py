# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
"""Coverage for host_agent.service create_agent_app branches and lifecycle."""

import asyncio
from pathlib import Path

import pytest

from host_agent.service import create_agent_app, start_agent_server, HostTlsConfig
from orchestrate import AgentCardLoader


class _Executor:
    async def execute(self, context, event_queue):
        del context, event_queue

    async def cancel(self, context, event_queue):
        del context, event_queue


def _secured_agent_card():
    cards = AgentCardLoader(
        Path(__file__).resolve().parents[1] / "samples" / "agentcard"
    ).get_all_agent_cards()
    return next(card for card in cards if card.name == "SPN Domain Agent City1")


def test_create_agent_app_supports_jsonrpc_binding():
    card = _secured_agent_card()
    card.supported_interfaces[0].protocol_binding = "JSONRPC"
    card.supported_interfaces[0].url = "http://127.0.0.1:1/a2a/jsonrpc"

    app = create_agent_app(card, _Executor())

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/a2a/jsonrpc" in paths


def test_create_agent_app_skips_interfaces_without_url():
    card = _secured_agent_card()
    card.supported_interfaces[0].url = ""

    app = create_agent_app(card, _Executor())

    # The empty-URL interface is skipped; the app still builds without its routes.
    assert app is not None


@pytest.mark.asyncio
async def test_https_with_tls_config_builds_ssl_kwargs_and_runs_lifecycle(tmp_path, monkeypatch):
    card = _secured_agent_card()
    for interface in card.supported_interfaces:
        interface.url = "https://127.0.0.1:8903/a2a/json"

    cert = tmp_path / "server.cer"
    cert.write_text("cert", encoding="utf-8")
    key = tmp_path / "server_key.pem"
    key.write_text("key", encoding="utf-8")
    pwd = tmp_path / "cert_pwd"
    pwd.write_text("secret", encoding="utf-8")

    served = {"called": False}

    class _FakeServer:
        def __init__(self, config):
            self.config = config

        async def serve(self):
            served["called"] = True

    monkeypatch.setattr("host_agent.service.uvicorn.Server", _FakeServer)

    events = []

    class _SyncHookExecutor(_Executor):
        def start(self):
            events.append("start")

        def aclose(self):
            events.append("aclose")

    await start_agent_server(
        card, _SyncHookExecutor(), 0, tls_config=HostTlsConfig(str(cert), str(key), str(pwd))
    )

    assert served["called"] is True
    assert events == ["start", "aclose"]


@pytest.mark.asyncio
async def test_start_agent_server_awaits_async_hooks_and_swallows_cancellation(monkeypatch):
    card = _secured_agent_card()
    for interface in card.supported_interfaces:
        interface.url = "http://127.0.0.1:8903/a2a/json"

    class _CancellingServer:
        def __init__(self, config):
            self.config = config

        async def serve(self):
            raise asyncio.CancelledError()

    monkeypatch.setattr("host_agent.service.uvicorn.Server", _CancellingServer)

    events = []

    class _AsyncHookExecutor(_Executor):
        async def start(self):
            events.append("start")

        async def aclose(self):
            events.append("aclose")

    await start_agent_server(card, _AsyncHookExecutor(), 0)

    assert events == ["start", "aclose"]
