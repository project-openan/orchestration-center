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

"""Ports the orchestration application owns; adapters implement them.

The application layer (``orchestrate.server``, ``orchestrate.core``) depends on
this module only. Concrete databases are knowledge of the adapters, so a new
backend is added without touching business code.

Ports are split per repository rather than folded into one fat interface, so a
backend implements exactly the capabilities it really has (the file backend has
no user store; only the SQL backends do).
"""

from abc import ABC, abstractmethod
from contextlib import nullcontext
from enum import Enum
from typing import Any, Dict, List, Optional

from orchestrate.core.model.execution_record import ExecutionRecord
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.workflow_search_result import WorkflowSearchResult
from orchestrate.persistence.errors import StorageValidationError


class Capability(Enum):
    """Optional things a backend may support, declared instead of duck-probed."""

    USERS = "users"
    TRANSACTIONS = "transactions"
    DDL_IN_TRANSACTION = "ddl_in_transaction"


class PsopRepository(ABC):
    """PSOP documents. Implementations must raise on failure, never return empty."""

    @abstractmethod
    def save(self, psop: PSOP) -> str:
        """Insert or replace a PSOP and return its id."""

    @abstractmethod
    def get(self, psop_id: str) -> Optional[PSOP]:
        """Return the PSOP, or ``None`` when it does not exist."""

    @abstractmethod
    def list_summaries(self) -> List[WorkflowSearchResult]:
        """Return every PSOP as a search result, in a stable order."""

    @abstractmethod
    def delete(self, psop_id: str) -> bool:
        """Delete the PSOP; ``False`` when it was not there."""


class ExecutionRecordRepository(ABC):
    """Execution records: full documents plus flat list summaries."""

    @abstractmethod
    def save(self, record: ExecutionRecord) -> str:
        """Insert or replace an execution record and return its id."""

    @abstractmethod
    def list_summaries(self) -> List[Dict[str, Any]]:
        """Return flat summaries (``execution_id``/``started_at``/``status``/...)."""

    @abstractmethod
    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Return the full record, or ``None`` when it does not exist."""

    @abstractmethod
    def delete(self, execution_id: str) -> bool:
        """Delete the record; ``False`` when it was not there."""


class PreflowRepository(ABC):
    """PreFlows. File-backed in every mode today, but a real port nonetheless."""

    @abstractmethod
    def save(self, preflow: PreFlow) -> str:
        """Insert or replace a PreFlow and return its id."""

    @abstractmethod
    def get(self, preflow_id: str) -> Optional[PreFlow]:
        """Return the PreFlow, or ``None`` when it does not exist."""

    @abstractmethod
    def list_ids(self) -> List[str]:
        """Return every PreFlow id, in a stable order."""

    @abstractmethod
    def delete(self, preflow_id: str) -> bool:
        """Delete the PreFlow; ``False`` when it was not there."""


class UserRepository(ABC):
    """Operator accounts. Only the SQL backends implement this port."""

    @abstractmethod
    def has_any(self) -> bool:
        """True when at least one account exists.

        Must raise :class:`StorageUnavailableError` when the store cannot be
        reached: authentication fails closed, so "unreachable" must never look
        like "no accounts configured".
        """

    @abstractmethod
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Return the account (upgrading its legacy hash when needed), or ``None``."""

    @abstractmethod
    def create(self, username: str, password: str, role: str, must_change_password: bool) -> bool:
        """Create an account; ``False`` when it already exists."""

    @abstractmethod
    def list_accounts(self) -> List[Dict[str, Any]]:
        """Return every account as a flat dict (never including the password hash)."""

    @abstractmethod
    def delete(self, username: str) -> bool:
        """Delete an account; ``False`` when it was not there."""

    @abstractmethod
    def update_password(self, username: str, new_password: str) -> bool:
        """Replace an account's stored credential; ``False`` on unknown user.

        NOTE (P2): the target contract turns the self-service change into a
        compare-and-swap against the credential triple it authenticated with,
        and keeps any unconditional reset as a separate, explicitly named
        method. P1 keeps today's signature so the structural move stays
        behavior preserving.
        """


class PersistenceBackend(ABC):
    """A configured storage backend: lifecycle plus the repositories it provides."""

    #: Value of ``persistence_mode`` this backend is selected by.
    mode: str = ""
    #: Capabilities this backend really implements.
    capabilities: frozenset = frozenset()

    def operation_scope(self):
        """Bind legacy/extension handlers to this backend for one operation.

        Backends without implicit connection state need no additional scope.
        """
        return nullcontext()

    @abstractmethod
    def check_ready(self) -> None:
        """Prove the backend is usable; raise :class:`StorageUnavailableError`."""

    @abstractmethod
    def initialize(self) -> None:
        """Create or migrate the schema. Idempotent; a no-op for file storage."""

    @abstractmethod
    def psops(self) -> PsopRepository:
        """Return the PSOP repository."""

    @abstractmethod
    def executions(self) -> ExecutionRecordRepository:
        """Return the execution-record repository."""

    @abstractmethod
    def preflows(self) -> PreflowRepository:
        """Return the PreFlow repository."""

    @abstractmethod
    def psops_for(self, storage: Any) -> PsopRepository:
        """Return a PSOP repository bound to a storage the caller already owns.

        In file mode the returned repository reads that storage, not the
        process-wide singleton; database backends ignore the argument. Keeping
        this on the port is what lets a call site stay free of mode branches.
        """

    def preflows_for(self, storage):
        return self.preflows()

    def documents(self):
        """Revisioned operational documents; adapters must explicitly implement it."""
        raise StorageValidationError(f"'{self.mode}' has no document repository")

    def users(self) -> UserRepository:
        """Return the user repository; only backends with ``Capability.USERS`` do."""
        raise StorageValidationError(f"'{self.mode}' has no user store")

    @abstractmethod
    def close(self) -> None:
        """Release pooled resources. Safe to call more than once."""
