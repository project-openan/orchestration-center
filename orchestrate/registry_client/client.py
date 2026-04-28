# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

import requests
from a2a.types import AgentCard
from loguru import logger


class AgentRegistryClient:
    """
    Client SDK for interacting with Agent Registry REST API.
    """

    def __init__(self, base_url: str, timeout: int = 30):
        """
        :param base_url: the base URL of the agent registry server, e.g. "http://localhost:8080"
        :param timeout: Request Timeout in seconds.
        """
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request and handel common errors
        """
        url = f"{self.base_url}{path}"
        kwargs.setdefault('timeout', self.timeout)
        try:
            resp = self.session.request(method=method, url=url, **kwargs)
            logger.info(f"request for :{url}, the result is {resp.json()}")
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise e

    def register(self, agent: Union[AgentCard, dict]) -> bool:
        """
        Register a new agent
        :param agent: AgentCard instance
        :return: True if successful, False if duplicate
        """
        if isinstance(agent, AgentCard):
            data = agent.model_dump()
        else:
            data = agent
        resp = self._request('POST', '/rest/a2a-t/v1/agents/register', json=data)
        return resp.json()

    def update_full(self, name: str, organization: str, agent: AgentCard) -> bool:
        """
        Fully replace an agent.
        :param name: Agent name(must match agent.name)
        :param organization: Agent organization(must match agent.provider.organization)
        :param agent: New AgentCard data
        :return: True if updated, False if not found
        """
        data = agent.model_dump()
        resp = self._request('PUT', f'/rest/a2a-t/v1/update_agent/{name}',
                             params={'organization': organization},
                             json=data)
        return resp.json()

    def deregister(self, name: str, organization: str) -> bool:
        """
        Deregister an agent.
        :param name: Agent name
        :param organization: Agent organization
        :return: True if deleted, False if not found
        """
        resp = self._request('DELETE', f'/rest/a2a-t/v1/deregister_agent/{name}',
                             params={'organization': organization})
        return resp.json()

    def get(self, name: str, organization: str) -> Optional[AgentCard]:
        """
        Get an agent by exact name and organization.
        :return: AgentCard if found, else None
        """
        resp = self._request('GET', f'/rest/a2a-t/v1/agents/{name}',
                             params={'organization': organization})
        if resp.status_code == 200:
            return AgentCard(**resp.json())
        elif resp.status_code == 404:
            return None
        else:
            resp.raise_for_status()
            return None

    def list_exact(self, name: Optional[str] = None, organization: Optional[str] = None,
                   provider: Optional[str] = None) -> List[AgentCard]:
        """
        Exact search. All parameters optional.
        :return: List of matching AgentCard instances
        """
        parms = {}
        if name:
            parms['name'] = name
        if organization:
            parms['organization'] = organization
        if provider:
            parms['provider'] = provider
        resp = self._request('GET', f'/rest/a2a-t/v1/agents/query', params=parms)
        data = resp.json()
        return [AgentCard(**item) for item in data]

    def search_by_task(self, task: str) -> List[AgentCard]:
        """
        Fuzzy search using task description.
        :param task: Natural language task
        :return: List of relevant AgentCard instances
        """
        resp = self._request('GET', f'/rest/a2a-t/v1/agents/retrieve', params={'task': task})
        data = resp.json()
        return [AgentCard(**item) for item in data]

    def list_all(self) -> List[AgentCard]:
        """Return all registered agents."""
        return self.list_exact()
