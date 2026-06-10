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
from typing import Union, Dict, Any, Optional, List

import httpx
from a2a.types import AgentCard
from google.protobuf.json_format import MessageToDict
from loguru import logger


class AgentRegistryClient:
    """
    Async client SDK for interacting with Agent Registry REST API.
    """

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault('timeout', self.timeout)
        try:
            client = await self._get_client()
            resp = await client.request(method=method, url=url, **kwargs)
            resp.raise_for_status()
            logger.info(f"request for :{url}, status={resp.status_code}")
            return resp
        except httpx.HTTPError as e:
            logger.error(f"Request failed: {e}")
            raise e

    async def register(self, agent: Union[AgentCard, dict]) -> bool:
        if isinstance(agent, AgentCard):
            data = MessageToDict(agent)
        else:
            data = agent
        resp = await self._request('POST', '/rest/v1/registry-center/agent-cards', json={"agentCards":[data]})
        return resp.json()

    async def update_full(self, name: str, organization: str, agent: AgentCard) -> bool:
        data = MessageToDict(agent)
        resp = await self._request('PUT', f'/rest/v1/registry-center/agent-cards/{organization}/{name}',
                             json={"agentCards":[data]})
        return resp.json()

    async def deregister(self, name: str, organization: str) -> bool:
        resp = await self._request('DELETE', f'/rest/v1/registry-center/agent-cards/{organization}/{name}')
        return resp.json()

    async def get(self, name: str, organization: str) -> dict | None:
        resp = await self._request('GET', f'/rest/v1/registry-center/agent-cards/{organization}/{name}')
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None
        else:
            resp.raise_for_status()
            return None

    async def list_exact(self, name: Optional[str] = None, organization: Optional[str] = None,
                   provider: Optional[str] = None) -> List[dict]:
        params = {}
        if name:
            params['name'] = name
        if organization:
            params['organization'] = organization
        if provider:
            params['provider'] = provider
        resp = await self._request('GET', f'/rest/v1/registry-center/agent-cards', params=params)
        try:
            data = resp.json()
        except Exception:
            logger.warning(f"Registry returned non-JSON response, status={resp.status_code}")
            return []
        agent_card =  data.get("agentCards", [])
        data_card = data.get("data", [])
        return agent_card or data_card

    async def search_by_task(self, task: str) -> List[dict]:
        resp = await self._request('POST', f'/rest/v1/registry-center/agent-cards/semantic-query', json={'task': task})
        return resp.json()

    async def list_all(self) -> List[dict]:
        return await self.list_exact()
