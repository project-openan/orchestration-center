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

"""SQL backends (PostgreSQL and MySQL) behind the storage ports.

The shared SQL processors are called inside an instance-bound connection/dialect scope.
Connection settings resolve once, at first startup I/O; constructors remain offline.
Both SQL brands share this class because the current code is already
brand-agnostic at this level -- the brand-specific knowledge lives in
``database.utils.sql_dialect`` and the two connection modules.
"""

from functools import wraps
from database.utils.connection_provider import SqlConnectionProvider, connection_scope, current_provider

from typing import Any, Dict, List, Optional

from loguru import logger

from orchestrate.core.model.execution_record import ExecutionRecord
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.workflow_search_result import WorkflowSearchResult
from common.custom import HandlerRegistry, InterfaceType
from common.util.persistence_mode import persistence_mode
from orchestrate.handlers import execution_record_processor as execution_records
from orchestrate.handlers import psop_processor as psops
from orchestrate.persistence.document_models import DocumentPreflowRepository
from orchestrate.persistence.contracts import (
    Capability,
    ExecutionRecordRepository,
    PersistenceBackend,
    PreflowRepository,
    PsopRepository,
    UserRepository,
)
from orchestrate.persistence.errors import StorageConfigError, StorageUnavailableError


def _ensure_mode(source_mode: str) -> None:
    """Ensure an operation uses the instance-scoped connection and dialect."""
    if current_provider() is not None and current_provider().mode == source_mode:
        return
    active = persistence_mode()
    if active != source_mode:
        raise StorageConfigError(
            f"this repository is bound to '{source_mode}' but persistence_mode='{active}': "
            "refusing to operate against a different database"
        )


def _bound(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with connection_scope(self._provider):
            return method(self, *args, **kwargs)
    return call


class _SqlPsopRepository(PsopRepository):
    def __init__(self, mode: str, provider) -> None:
        self._mode = mode
        self._provider = provider

    @_bound
    def save(self, psop: PSOP) -> str:
        _ensure_mode(self._mode)
        return psops.custom_save_psop(psop)

    @_bound
    def get(self, psop_id: str) -> Optional[PSOP]:
        _ensure_mode(self._mode)
        # An extension that replaced the bundled query handler wins here too.
        # Reads must not take a different path from writes: before this, a
        # deployment with a custom GET_PSOP_BY_ID saved through its handler and
        # then failed to read the row back through the built-in query.
        override = HandlerRegistry.get_extension_override(InterfaceType.GET_PSOP_BY_ID)
        if override is not None:
            logger.debug("[Persistence] GET_PSOP_BY_ID served by a registered extension")
            return override().handle(psop_id)
        return psops.get_psop_by_id(psop_id)

    @_bound
    def list_summaries(self) -> List[WorkflowSearchResult]:
        _ensure_mode(self._mode)
        override = HandlerRegistry.get_extension_override(InterfaceType.GET_ALL_PSOP)
        if override is not None:
            logger.debug("[Persistence] GET_ALL_PSOP served by a registered extension")
            return override().handle()
        return psops.get_all_psops()

    @_bound
    def delete(self, psop_id: str) -> bool:
        _ensure_mode(self._mode)
        return psops.custom_delete_psop(psop_id)


class _SqlExecutionRecordRepository(ExecutionRecordRepository):
    def __init__(self, mode: str, provider) -> None:
        self._mode = mode
        self._provider = provider

    @_bound
    def save(self, record: ExecutionRecord) -> str:
        _ensure_mode(self._mode)
        return execution_records.db_save_execution_record(record)

    @_bound
    def list_summaries(self) -> List[Dict[str, Any]]:
        _ensure_mode(self._mode)
        return execution_records.db_list_execution_records()

    @_bound
    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        _ensure_mode(self._mode)
        return execution_records.db_get_execution_record(execution_id)

    @_bound
    def delete(self, execution_id: str) -> bool:
        _ensure_mode(self._mode)
        return execution_records.db_delete_execution_record(execution_id)


class _SqlUserRepository(UserRepository):
    """Delegates to ``database.utils.user_store`` (moved into the SQL layer in P2)."""

    def __init__(self, mode: str, provider) -> None:
        self._mode = mode
        self._provider = provider

    @_bound
    def has_any(self) -> bool:
        _ensure_mode(self._mode)
        from database.utils.user_store import has_any_user

        return has_any_user()

    @_bound
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        _ensure_mode(self._mode)
        from database.utils.user_store import authenticate_user

        return authenticate_user(username, password)

    @_bound
    def create(self, username: str, password: str, role: str, must_change_password: bool) -> bool:
        _ensure_mode(self._mode)
        from database.utils.user_store import create_user

        return create_user(username, password, role=role, must_change_password=must_change_password)

    @_bound
    def list_accounts(self) -> List[Dict[str, Any]]:
        _ensure_mode(self._mode)
        from database.utils.user_store import list_users

        return list_users()

    @_bound
    def delete(self, username: str) -> bool:
        _ensure_mode(self._mode)
        from database.utils.user_store import delete_user

        return delete_user(username)

    @_bound
    def update_password(self, username: str, new_password: str) -> bool:
        _ensure_mode(self._mode)
        from database.utils.user_store import update_password

        return update_password(username, new_password)


class SqlPersistenceBackend(PersistenceBackend):
    """``persistence_mode=postgresql`` or ``mysql``; brand details live below this line."""

    def operation_scope(self):
        """Use this instance's connection provider, including extension calls."""
        return connection_scope(self._provider)

    capabilities = frozenset({Capability.USERS})

    def __init__(self, mode: str, conf: Optional[dict] = None, storage=None) -> None:
        self.mode = mode
        self._conf = conf or {}
        self._provider = SqlConnectionProvider(mode, self._conf.get('connection_config'))
        from orchestrate.persistence.documents import SqlDocuments
        self._documents = SqlDocuments(self._provider)
        self._psops = _SqlPsopRepository(mode, self._provider)
        self._executions = _SqlExecutionRecordRepository(mode, self._provider)
        self._users = _SqlUserRepository(mode, self._provider)
        self._preflows = DocumentPreflowRepository(self._documents)

    @_bound
    def check_ready(self) -> None:
        """Fail at startup, not at request time: right database, and reachable."""
        from database.utils.db_connection import create_connection

        _ensure_mode(self.mode)
        conn = create_connection()
        if conn is None:
            raise StorageUnavailableError("Unable to connect to database")
        try:
            conn.close()
        except Exception:  # pragma: no cover - defensive, closing must not mask readiness
            logger.warning("[Storage] Failed to close the readiness connection", exc_info=True)

    @_bound
    def initialize(self) -> None:
        """Create the schema, idempotently (today: ``table_creation.create_tables``)."""
        from database.utils.table_creation import create_tables

        _ensure_mode(self.mode)
        if str(self._conf.get("deployment_mode", "single")).lower() == "cluster":
            self._documents.check_ready()
            from orchestrate.server.sql_sessions import check_auth_schema
            check_auth_schema(self._provider)
            return
        create_tables()
        self._documents.initialize()
        from orchestrate.server.sql_sessions import ensure_auth_schema
        ensure_auth_schema(self._provider)

    def documents(self):
        return self._documents

    def psops(self) -> PsopRepository:
        return self._psops

    def executions(self) -> ExecutionRecordRepository:
        return self._executions

    def preflows(self) -> PreflowRepository:
        return self._preflows

    def users(self) -> UserRepository:
        return self._users

    def close(self) -> None:
        """Close only resources owned by this backend; safe after config changes."""
        self._provider.close()

    def psops_for(self, storage: Any = None) -> PsopRepository:
        """Rows live in the database, so the storage argument is ignored."""
        return self.psops()
