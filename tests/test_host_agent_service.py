# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from host_agent.service import create_agent_app, start_agent_server, HostTlsConfig
from orchestrate import AgentCardLoader
from samples.spn_host_agent.auth import SampleFixedCredentialAuth


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


def test_generic_host_server_does_not_install_demo_login_route():
    app = create_agent_app(_secured_agent_card(), _Executor())

    response = TestClient(app).post(
        "/rest/plat/smapp/v1/oauth/token",
        json={"username": "admin", "password": "Admin@123"},
    )

    assert response.status_code == 404


def test_sample_auth_provider_owns_demo_credentials():
    app = create_agent_app(
        _secured_agent_card(),
        _Executor(),
        auth_provider=SampleFixedCredentialAuth(),
    )
    client = TestClient(app)

    rejected = client.post(
        "/rest/plat/smapp/v1/oauth/token",
        json={"username": "admin", "password": "wrong"},
    )
    accepted = client.post(
        "/rest/plat/smapp/v1/oauth/token",
        json={"username": "admin", "password": "Admin@123"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["accessSession"]

@pytest.mark.asyncio
async def test_https_missing_material_is_not_silently_http(tmp_path):
    card = _secured_agent_card()
    for interface in card.supported_interfaces:
        interface.url = "https://127.0.0.1:8903"
    with pytest.raises(ValueError, match="missing"):
        await start_agent_server(card, _Executor(), 0, tls_config=HostTlsConfig(
            str(tmp_path / "missing.cer"), str(tmp_path / "missing.pem")))


@pytest.mark.asyncio
async def test_host_http_mixed_protocols_are_rejected():
    card = _secured_agent_card()
    del card.supported_interfaces[:]
    card.supported_interfaces.add(url="http://127.0.0.1:8903", protocol_binding="JSONRPC")
    card.supported_interfaces.add(url="https://127.0.0.1:8903", protocol_binding="HTTP+JSON")
    with pytest.raises(ValueError, match="single"):
        await start_agent_server(card, _Executor(), 0)
