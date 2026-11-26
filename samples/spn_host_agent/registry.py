# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sample composition adapter using the center's registry auth/TLS settings."""

import json

from a2a.types import AgentCard
from google.protobuf.json_format import Parse

from orchestrate.agentcard_loader import _normalize_agent_dict
from orchestrate.registry_client.client_factory import AgentRegistryClientFactory


class ConfiguredRegistryCardProvider:
    """Keep registry credentials in the sample composition, not the Host runtime.

    Released workflow-engine 0.0.9's RegistryClient cannot attach Bearer tokens.
    The center's configured client supports that contract and independent TLS
    identity, without requiring an unpublished SDK or weakening registry auth.
    """

    def __init__(self, registry_url: str, config: dict):
        self._url = registry_url
        self._factory = AgentRegistryClientFactory(config=dict(config))

    async def load(self) -> list[AgentCard]:
        client = self._factory.create_client(base_url=self._url)
        try:
            raw = await client.list_exact()
            return [Parse(json.dumps(_normalize_agent_dict(card)), AgentCard()) for card in raw]
        finally:
            await client.close()
