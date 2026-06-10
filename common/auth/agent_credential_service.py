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

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import httpx
from a2a.client.auth import CredentialService
from a2a.client.auth import InMemoryContextCredentialStore as _SDKCredentialStore
from loguru import logger

_CREDENTIAL_CONFIG_FILENAME = "agent_credentials.json"


class AgentCredentialService(CredentialService):
    """Credential service that obtains tokens via login endpoint for agents requiring Bearer auth.

    For agents whose securitySchemes specify Bearer auth with a login flow,
    this service POSTs credentials to the login URL and caches the resulting
    access token.  Each agent gets its own service instance so that scheme
    name alone is sufficient to resolve credentials.
    """

    def __init__(
        self,
        agent_name: str,
        scheme_configs: Dict[str, dict],
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        self._agent_name = agent_name
        self._schemes = scheme_configs
        self._httpx_client = httpx_client
        self._tokens: Dict[str, tuple] = {}
        self._lock = None

    def _ensure_lock(self):
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()

    def set_httpx_client(self, client: httpx.AsyncClient):
        self._httpx_client = client

    async def get_credentials(
        self,
        security_scheme_name: str,
        context=None,
    ) -> Optional[str]:
        scheme_cfg = self._schemes.get(security_scheme_name)
        if not scheme_cfg:
            return None

        cached = self._tokens.get(security_scheme_name)
        if cached:
            token, expires_at = cached
            if time.time() < expires_at - 60:
                return token

        self._ensure_lock()
        async with self._lock:
            cached = self._tokens.get(security_scheme_name)
            if cached:
                token, expires_at = cached
                if time.time() < expires_at - 60:
                    return token

            token = await self._login(scheme_cfg)
            if token:
                ttl = scheme_cfg.get("token_ttl", 3600)
                self._tokens[security_scheme_name] = (token, time.time() + ttl)
                logger.info(
                    f"[AgentAuth] Obtained token for agent '{self._agent_name}' "
                    f"scheme '{security_scheme_name}', TTL={ttl}s"
                )
            return token

    async def _login(self, scheme_cfg: dict) -> Optional[str]:
        login_url = scheme_cfg.get("login_url")
        if not login_url:
            logger.warning(
                f"[AgentAuth] Missing login_url for agent '{self._agent_name}'"
            )
            return None

        request_fields = scheme_cfg.get("request_fields")
        if request_fields and isinstance(request_fields, dict):
            body = dict(request_fields)
        else:
            username = scheme_cfg.get("username")
            password = scheme_cfg.get("password")
            if not username or not password:
                logger.warning(
                    f"[AgentAuth] Incomplete credentials for agent '{self._agent_name}': "
                    f"username={'set' if username else 'MISSING'}, "
                    f"password={'set' if password else 'MISSING'}"
                )
                return None
            username_field = scheme_cfg.get("username_field", "username")
            password_field = scheme_cfg.get("password_field", "password")
            body = {
                username_field: username,
                password_field: password,
            }

        method = scheme_cfg.get("method", "POST").upper()
        token_field = scheme_cfg.get("token_field", "accessSession")

        client = self._httpx_client
        if client is None:
            timeout_config = httpx.Timeout(connect=30, read=30, write=30, pool=5.0)
            client = httpx.AsyncClient(timeout=timeout_config, verify=False)
            own_client = True
        else:
            own_client = False

        try:
            logger.info(
                f"[AgentAuth] Logging in for agent '{self._agent_name}' "
                f"[{method}] {login_url}"
            )
            resp = await client.request(
                method,
                login_url,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict):
                token = data.get(token_field)
                if not token:
                    token = data.get("accessSession") or data.get("access_session") or data.get("token")
            else:
                token = None

            if token:
                logger.info(
                    f"[AgentAuth] Login succeeded for agent '{self._agent_name}'"
                )
                return token

            logger.warning(
                f"[AgentAuth] Token field '{token_field}' not found in login response "
                f"for agent '{self._agent_name}'. Response keys: {list(data.keys()) if isinstance(data, dict) else 'non-dict'}"
            )
            return None
        except Exception as e:
            logger.error(
                f"[AgentAuth] Login failed for agent '{self._agent_name}': {e}"
            )
            return None
        finally:
            if own_client:
                await client.aclose()


class AgentAuthManager:
    """Singleton that loads agent credentials from config and creates per-agent CredentialService instances."""

    _instance: Optional["AgentAuthManager"] = None

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or self._default_config_path()
        self._config: Dict[str, dict] = {}
        self._services: Dict[str, AgentCredentialService] = {}
        self._load_config()

    @staticmethod
    def _default_config_path() -> Path:
        return Path(__file__).resolve().parent.parent.parent / "etc" / "conf" / _CREDENTIAL_CONFIG_FILENAME

    def _load_config(self):
        path = Path(self._config_path)
        if not path.exists():
            logger.debug(f"[AgentAuth] Credential config not found at {path}, agent auth disabled")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            if self._config:
                logger.info(f"[AgentAuth] Loaded credentials for agents: {list(self._config.keys())}")
        except Exception as e:
            logger.warning(f"[AgentAuth] Failed to load credential config: {e}")
            self._config = {}

    def get_service(self, agent_name: str) -> Optional[AgentCredentialService]:
        if agent_name in self._services:
            return self._services[agent_name]

        agent_creds = self._config.get(agent_name)
        if not agent_creds:
            return None

        service = AgentCredentialService(agent_name, agent_creds)
        self._services[agent_name] = service
        logger.info(f"[AgentAuth] Created credential service for agent '{agent_name}'")
        return service

    def set_httpx_client(self, client: httpx.AsyncClient):
        for svc in self._services.values():
            svc.set_httpx_client(client)

    @classmethod
    def get_instance(cls) -> "AgentAuthManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def get_auth_manager() -> AgentAuthManager:
    return AgentAuthManager.get_instance()
