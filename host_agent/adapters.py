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

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from workflow_engine import A2ATransport, RegistryClient, WorkflowEngineClient


class AgentCardProvider(Protocol):
    async def load(self) -> list[Any]: ...


class EngineClientFactory(Protocol):
    def create(self, agent_cards: list[Any], *, auth_provider: Any | None = None): ...


class RegistryAgentCardProvider:
    """Load the current AgentCards from a registry service."""

    def __init__(self, registry_url: str, *, ssl_verify: bool = False) -> None:
        self._registry_url = registry_url
        self._ssl_verify = ssl_verify

    async def load(self) -> list[Any]:
        registry = RegistryClient(self._registry_url, ssl_verify=self._ssl_verify)
        return await registry.fetch_agent_cards()


class DefaultEngineClientFactory:
    """Build an owning workflow-engine client for one HostAgent execution."""

    def __init__(
        self,
        *,
        credentials_config: str | dict | None = None,
        ssl_verify: bool = False,
        max_negotiation_exchanges: int = 3,
        transport_factory: Callable[..., Any] = A2ATransport,
        auth_provider: Any | None = None,
    ) -> None:
        self._credentials_config = credentials_config
        self._ssl_verify = ssl_verify
        self._max_negotiation_exchanges = max_negotiation_exchanges
        self._transport_factory = transport_factory
        self._auth_provider = auth_provider

    def create(self, agent_cards: list[Any], *, auth_provider: Any | None = None):
        provider = auth_provider if auth_provider is not None else self._auth_provider
        transport_kwargs: dict[str, Any] = {
            "agent_cards": agent_cards,
            "credentials_config": self._credentials_config,
            "ssl_verify": self._ssl_verify,
        }
        if provider is not None:
            transport_kwargs["auth_provider"] = provider
        transport = self._transport_factory(**transport_kwargs)
        return WorkflowEngineClient.owning(
            transport,
            max_negotiation_exchanges=self._max_negotiation_exchanges,
        )
