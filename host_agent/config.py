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

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from host_agent.role_contract import ExecutionScope, RoleBinding

if TYPE_CHECKING:
    from workflow_engine import TaskRequest


@dataclass(frozen=True, slots=True)
class HostAgentConfig:
    """Runtime settings supplied by the host application's composition root."""

    orchestration_url: str
    registry_url: str
    ssl_verify: bool = False
    max_negotiation_exchanges: int = 3
    # Header names the host accepts as authentication output from an
    # injected AuthProvider, beyond what the card's schemes imply.
    custom_auth_headers: tuple[str, ...] = ()
    role_dispatch_key: str = field(default_factory=lambda: os.environ.get("ORCH_ROLE_DISPATCH_KEY", ""), repr=False)
    # Deployment admission (REQ74 P4): role dispatch is disabled by default;
    # the signature key alone never enables the capability.
    role_execution_mode: str = "disabled"
    deployment_environment: str = "production"

    def __post_init__(self) -> None:
        if not self.orchestration_url:
            raise ValueError("orchestration_url is required")
        if not self.registry_url:
            raise ValueError("registry_url is required")
        if self.max_negotiation_exchanges < 1:
            raise ValueError("max_negotiation_exchanges must be positive")

    def role_execution_admitted(self) -> tuple[bool, list[str]]:
        """Shared deployment-policy decision (see host_agent.role_contract)."""
        from host_agent.role_contract import role_execution_admitted

        return role_execution_admitted(self.role_execution_mode, self.deployment_environment)


@dataclass(frozen=True, slots=True)
class RoleTaskIdentity:
    """Original PSOP position and the corresponding SDK callback identifiers."""

    task_id: str
    step_name: str
    subtask_index: int
    sdk_execution_id: str
    sdk_task_id: str


@dataclass(frozen=True, slots=True)
class RoleExecutionContext:
    """Validated center context; callback IDs belong to the SDK's namespace."""

    execution_id: str
    caller_id: str
    scope: ExecutionScope
    bindings: tuple[RoleBinding, ...]
    _task_identities: Mapping[tuple[str, str], RoleTaskIdentity] = field(
        default_factory=lambda: MappingProxyType({}), repr=False, compare=False,
    )

    def task_identity(self, request: TaskRequest) -> RoleTaskIdentity:
        """Resolve a callback after the Host has registered its task event."""
        identity = self._task_identities.get((request.execution_id, request.task_id))
        if identity is None or identity.step_name != request.step_name:
            raise LookupError("Callback has no verified PSOP task mapping")
        return identity

    def binding_for(self, request: TaskRequest) -> RoleBinding | None:
        """Return the original role binding, or None for a mapped instance task.

        Unknown callbacks raise LookupError; they never fall back to matching
        an agent name or skill, which need not be unique within a workflow.
        """
        task_id = self.task_identity(request).task_id
        return next((binding.model_copy(deep=True) for binding in self.bindings
                     if binding.task_id == task_id), None)


@dataclass(frozen=True, slots=True)
class ControlPointContext:
    """Request-scoped values made available to a business policy factory."""

    orchestration_url: str
    ssl_verify: bool
    lang: str
    role_execution: RoleExecutionContext | None = None
