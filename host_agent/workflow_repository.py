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

from typing import Any

from workflow_engine import HttpAuthProvider, load_psop, search_psop


class OrchestrationWorkflowRepository:
    """HTTP adapter for workflows owned by the Orchestration Center."""

    def __init__(
        self,
        *,
        orch_url: str,
        ssl_verify: bool = False,
        auth_provider: HttpAuthProvider | None = None,
        ca_certs_path: str | None = None,
        client_cert_path: str | None = None,
        client_key_path: str | None = None,
        client_key_password: str | None = None,
        crl_path: str | None = None,
    ) -> None:
        self._orch_url = orch_url.rstrip("/")
        # The SDK owns authentication, renewal and TLS validation. Keep the same
        # provider across search/load calls so its token cache is shared.
        self._request_options: dict[str, Any] = {"ssl_verify": ssl_verify}
        self._request_options.update(
            {
                name: value
                for name, value in {
                    "auth_provider": auth_provider,
                    "ca_certs_path": ca_certs_path,
                    "client_cert_path": client_cert_path,
                    "client_key_path": client_key_path,
                    "client_key_password": client_key_password,
                    "crl_path": crl_path,
                }.items()
                if value is not None
            }
        )

    async def find(self, intent: str) -> Any:
        results = await search_psop(
            self._orch_url,
            intent,
            top_n=3,
            **self._request_options,
        )
        if not results:
            raise RuntimeError("No matching workflow found")
        return await self.get(results[0].workflow_id)

    async def get(self, psop_id: str) -> Any:
        workflow = await load_psop(
            self._orch_url,
            psop_id,
            **self._request_options,
        )
        return workflow
