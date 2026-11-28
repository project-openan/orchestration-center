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

from functools import lru_cache
import inspect
import os
from typing import Any

from loguru import logger

from workflow_engine import HttpAuthProvider, load_psop, search_psop


def host_resolution(workflow) -> tuple[str | None, bool]:
    """``(declared host, ambiguous)`` for a workflow.

    Released SDK versions do not expose ``declared_host()`` yet, so the same rule is derived here
    from the step/task model: an explicit ``workflow_host`` wins, else the agent a SelfLoop task
    runs on. ``ambiguous`` means the definition names more than one host (or the SDK rejects it);
    such a workflow must not be claimed by whichever host happens to search first.
    """
    getter = getattr(workflow, "declared_host", None)
    if callable(getter):
        try:
            return getter(), False
        except (TypeError, ValueError):
            return None, True
    names: list[str] = []
    for step in getattr(workflow, "steps", None) or []:
        if "self" not in str(getattr(step, "step_type", "") or "").lower():
            continue
        for task in getattr(step, "subtasks", None) or []:
            agent = str(getattr(task, "agent", "") or "").strip()
            if agent and agent not in names:
                names.append(agent)
    declared = str(getattr(workflow, "workflow_host", "") or "").strip()
    if declared:
        return declared, any(name != declared for name in names)
    if len(names) > 1:
        return None, True
    return (names[0] if names else None), False


def declared_host(workflow) -> str | None:
    return host_resolution(workflow)[0]


@lru_cache(maxsize=1)
def _load_psop_accepts_revision() -> bool:
    try:
        parameters = inspect.signature(load_psop).parameters
    except (TypeError, ValueError):
        return True
    return ("revision" in parameters
            or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()))


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
        host_name: str | None = None,
    ) -> None:
        self._orch_url = orch_url.rstrip("/")
        self._host_name = host_name
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
        # The demo host may carry a center-issued PSOP token instead of an account.
        token = os.environ.get("OPENAN_PSOP_ACCESS_TOKEN")
        if token and "auth_provider" not in self._request_options:
            self._request_options["access_token"] = token

    async def find(self, intent: str) -> Any:
        results = await search_psop(
            self._orch_url,
            intent,
            top_n=3,
            **self._request_options,
        )
        if not results:
            raise RuntimeError("No matching workflow found")
        for result in results:
            try:
                workflow = await self.get(result.workflow_id)
            except Exception as error:  # one broken candidate must not hide the others
                logger.warning("Skipping workflow {} during host lookup ({}: {})",
                               result.workflow_id, type(error).__name__, error)
                continue
            declared, ambiguous = host_resolution(workflow)
            if ambiguous:
                logger.warning("Skipping workflow {}: it does not declare a single host",
                               result.workflow_id)
                continue
            if self._host_name is None or declared in {None, self._host_name}:
                if declared is None:
                    logger.info("Workflow {} declares no host; accepting it as a legacy definition",
                                result.workflow_id)
                return workflow
        raise RuntimeError(f"None of the matching workflows is executed by {self._host_name!r}")

    async def get(self, psop_id: str, *, revision: str | None = None) -> Any:
        revision_option = {"revision": revision} if revision is not None else {}
        if revision_option and not _load_psop_accepts_revision():
            logger.warning("Installed workflow engine has no revision support; loading the latest {}",
                           psop_id)
            revision_option = {}
        workflow = await load_psop(
            self._orch_url,
            psop_id,
            **revision_option,
            **self._request_options,
        )
        return workflow
