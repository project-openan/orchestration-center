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

"""File-backed adapters: today's JSON storage behind the storage ports.

This is the reference implementation of the ports. It wraps the existing
:class:`~orchestrate.core.persistence.WorkflowStorage` rather than replacing it,
so the on-disk format, atomic writes and validation keep behaving exactly as
before.

P1 scope note: these adapters pass the underlying exceptions through unchanged
(``WorkflowStorageError`` and friends). Unifying every backend on the
:mod:`orchestrate.persistence.errors` hierarchy is P1b's job, so this move stays
behavior preserving.
"""

from typing import Any, Dict, List, Optional

from orchestrate.core.model.execution_record import ExecutionRecord
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.task_summary import build_tasks_summary, generation_binding
from orchestrate.core.workflow_search_result import WorkflowSearchResult
from orchestrate.persistence.contracts import (
    Capability,
    ExecutionRecordRepository,
    PersistenceBackend,
    PreflowRepository,
    PsopRepository,
)
from orchestrate.workflow_storage_instance import get_workflow_storage


class FilePsopRepository(PsopRepository):
    def __init__(self, storage: WorkflowStorage) -> None:
        self._storage = storage

    def save(self, psop: PSOP) -> str:
        return self._storage.save_psop(psop)

    def get(self, psop_id: str) -> Optional[PSOP]:
        return self._storage.load_psop(psop_id)

    def list_summaries(self) -> List[WorkflowSearchResult]:
        summaries = []
        for workflow_id in self._storage.list_psops():
            psop = self._storage.load_psop(workflow_id)
            if not psop:
                continue
            summaries.append(WorkflowSearchResult(
                workflow_id=psop.id,
                workflow_type="psop",
                name=psop.name,
                description=psop.description,
                tags=psop.tags,
                created_at=psop.created_at,
                user_intent=psop.user_intent,
                related_preflow=psop.related_preflow,
                tasks_summary=build_tasks_summary(psop),
                binding=generation_binding(psop),
            ))
        return summaries

    def delete(self, psop_id: str) -> bool:
        return self._storage.delete_psop(psop_id)


class _FileExecutionRecordRepository(ExecutionRecordRepository):
    def __init__(self, storage: WorkflowStorage) -> None:
        self._storage = storage

    def save(self, record: ExecutionRecord) -> str:
        return self._storage.save_execution_record(record)

    def list_summaries(self) -> List[Dict[str, Any]]:
        # NOTE: ordered by file mtime, while the SQL backend orders by
        # started_at DESC. Both are a total order, but they are not the same
        # one; P2 aligns this on started_at with the primary key as tiebreak.
        return self._storage.list_execution_records()

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        return self._storage.load_execution_record(execution_id)

    def delete(self, execution_id: str) -> bool:
        return self._storage.delete_execution_record(execution_id)


class FilePreflowRepository(PreflowRepository):
    def __init__(self, storage: WorkflowStorage) -> None:
        self._storage = storage

    def save(self, preflow: PreFlow) -> str:
        return self._storage.save_preflow(preflow)

    def get(self, preflow_id: str) -> Optional[PreFlow]:
        return self._storage.load_preflow(preflow_id)

    def list_ids(self) -> List[str]:
        return self._storage.list_preflows()

    def delete(self, preflow_id: str) -> bool:
        return self._storage.delete_preflow(preflow_id)


class FilePersistenceBackend(PersistenceBackend):
    """JSON-on-disk backend (``persistence_mode=file``, the default)."""

    mode = "file"
    capabilities = frozenset()  # no user store, no transactions

    def __init__(self, conf: Optional[dict] = None,
                 storage: Optional[WorkflowStorage] = None) -> None:
        self._conf = conf or {}
        import os
        from orchestrate.persistence.documents import FileDocuments, data_root
        if storage is not None:
            self._storage = storage
        elif self._conf.get("data_dir") or os.environ.get("ORCH_DATA_DIR"):
            self._storage = WorkflowStorage(str(data_root(self._conf)))
        else:
            self._storage = get_workflow_storage()
        self._documents = FileDocuments(self._storage.psop_dir.parents[1])
        self._psops = FilePsopRepository(self._storage)
        self._executions = _FileExecutionRecordRepository(self._storage)
        self._preflows = FilePreflowRepository(self._storage)

    def check_ready(self) -> None:
        """File storage needs no readiness probe; the directory is created lazily."""

    def initialize(self) -> None:
        """Seed the default workflow library into file storage.

        Parallel to the SQL backend's ``initialize()`` (which creates the
        schema and imports the default data): file persistence mode never
        touches the database, so the shipped default PSOP workflows are
        materialized here. Idempotent and non-blocking - a seeding failure
        must not keep the server from starting.
        """
        from loguru import logger

        from database.utils.seed_data import seed_default_psops_to_file_storage

        try:
            seed_default_psops_to_file_storage(target_dir=self._storage.psop_dir)
        except Exception as e:
            logger.error(f"Default workflow seeding into file storage failed (non-blocking): {e}")

    def preflows_for(self, storage):
        return FilePreflowRepository(storage)

    def documents(self):
        return self._documents

    def psops(self) -> PsopRepository:
        return self._psops

    def executions(self) -> ExecutionRecordRepository:
        return self._executions

    def preflows(self) -> PreflowRepository:
        return self._preflows

    def close(self) -> None:
        """Nothing pooled; kept so callers can always call ``close()``."""

    def psops_for(self, storage: WorkflowStorage) -> PsopRepository:
        """Bind the PSOP repository to the storage the caller already owns."""
        return FilePsopRepository(storage)
