# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock

import httpx
import pytest

from samples.spn_host_agent.registry import ConfiguredRegistryCardProvider


@pytest.mark.asyncio
async def test_sample_registry_provider_uses_configured_token_and_closes(monkeypatch):
    monkeypatch.setenv('SYNTHETIC_REGISTRY_TOKEN', 'synthetic-registry-token')
    provider = ConfiguredRegistryCardProvider('http://registry.invalid', {
        'agent_registry.token_env': 'SYNTHETIC_REGISTRY_TOKEN', 'ssl_verify': True,
    })
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers['Authorization'] == 'Bearer synthetic-registry-token'
        return httpx.Response(200, json={'agentCards': [{
            'name': 'Synthetic Worker', 'version': '1.0',
            'skills': [], 'supportedInterfaces': [],
        }]})

    client = provider._factory.create_client(base_url=provider._url)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond), headers=client.headers)
    monkeypatch.setattr(provider._factory, 'create_client', lambda **_: client)
    cards = await provider.load()
    assert [card.name for card in cards] == ['Synthetic Worker']
    assert requests[0].url.path == '/rest/v1/registry-center/agent-cards'
    assert client._client is None


@pytest.mark.asyncio
async def test_sample_registry_provider_does_not_swallow_registry_failures(monkeypatch):
    provider = ConfiguredRegistryCardProvider('http://registry.invalid', {})
    client = AsyncMock()
    client.list_exact.side_effect = RuntimeError('synthetic registry unavailable')
    monkeypatch.setattr(provider._factory, 'create_client', lambda **_: client)
    with pytest.raises(RuntimeError, match='registry unavailable'):
        await provider.load()
    client.close.assert_awaited_once()
