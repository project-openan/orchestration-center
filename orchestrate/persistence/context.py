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

"""The single storage facade the application layer is allowed to depend on.

Built exactly once, in the composition root (``orchestrate/start.py``), and then
handed to the HTTP layer and to the engine. Business code asks this object for a
repository; it never reads ``persistence_mode`` or imports a driver itself.
"""

from typing import Optional

from orchestrate.persistence.contracts import (
    Capability,
    ExecutionRecordRepository,
    PersistenceBackend,
    PreflowRepository,
    PsopRepository,
    UserRepository,
)


class StorageContext:
    """Repositories of the configured backend, resolved once at startup."""

    def __init__(self, backend: PersistenceBackend) -> None:
        self._backend = backend
        backend_mode = getattr(backend, "mode", "") or ""
        if not backend_mode:
            raise ValueError("storage backend must declare its mode")
        self.mode = backend_mode
        self._psops: Optional[PsopRepository] = None
        self._executions: Optional[ExecutionRecordRepository] = None
        self._preflows: Optional[PreflowRepository] = None

        # Resolve eagerly: a broken adapter should fail at startup, not on the
        # first request that happens to need one repository.
        self._psops = backend.psops()
        self._executions = backend.executions()
        self._preflows = backend.preflows()

    @property
    def documents(self):
        return self._backend.documents()

    def transaction(self):
        return self.documents.transaction()

    @property
    def backend(self) -> PersistenceBackend:
        """The configured backend, for lifecycle calls and diagnostics."""
        return self._backend

    @property
    def psops(self) -> PsopRepository:
        """PSOP repository."""
        return self._psops

    @property
    def executions(self) -> ExecutionRecordRepository:
        """Execution-record repository."""
        return self._executions

    @property
    def preflows(self) -> PreflowRepository:
        """PreFlow repository."""
        return self._preflows

    @property
    def has_users(self) -> bool:
        """True when this backend stores operator accounts itself."""
        return Capability.USERS in (self._backend.capabilities or frozenset())

    @property
    def users(self) -> UserRepository:
        """User repository; raises when the backend has no user store."""
        return self._backend.users()

    def supports(self, capability: Capability) -> bool:
        """True when the configured backend declares ``capability``."""
        return capability in (self._backend.capabilities or frozenset())

    def check_ready(self) -> None:
        """Prove the backend is usable before the server binds a port."""
        self._backend.check_ready()

    def initialize(self) -> None:
        """Create or migrate the schema (idempotent)."""
        self._backend.initialize()

    def close(self) -> None:
        """Release pooled resources; registered as the shutdown hook."""
        self._backend.close()

    def preflows_for(self, storage):
        return self._backend.preflows_for(storage)

    def psops_for(self, storage) -> PsopRepository:
        """PSOP repository for a caller that owns its own file storage."""
        return self._backend.psops_for(storage)


_persistence_context: Optional[StorageContext] = None


def configure_context(context: StorageContext) -> StorageContext:
    """Install the process-wide context. Called once by the composition root."""
    global _persistence_context
    _persistence_context = context
    return context


def current_context() -> StorageContext:
    """Return the configured context, or lazily build the file-mode one.

    The app is a module-level FastAPI global that tests import directly, so the
    composition root is not guaranteed to have run. Defaulting to the file
    backend keeps that case working and preserves the historical default of
    ``persistence_mode=file``.
    """
    global _persistence_context
    if _persistence_context is None:
        from orchestrate.persistence.factory import build_context

        _persistence_context = build_context()
    return _persistence_context
