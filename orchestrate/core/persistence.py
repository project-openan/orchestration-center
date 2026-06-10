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
import re
import tempfile
import os
from loguru import logger
from pathlib import Path
from typing import Optional, List, Dict, Any

from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.execution_record import ExecutionRecord

class WorkflowStorageError(Exception):
    """Exception raised for workflow storage errors."""
    pass


class WorkflowStorage:
    """Storage for workflows (PSOP and PreFlow)."""
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize workflow storage.

        Args:
            storage_dir: Storage directory path, defaults to data/workflow_storage under project root
        """
        if storage_dir is None:
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            self.psop_dir = project_root / "data" / "workflow_storage" / "psop"
            self.preflow_dir = project_root / "data" / "workflow_storage" / "preflow"
            self.execution_dir = project_root / "data" / "workflow_storage" / "execution_records"
        else:
            base = Path(storage_dir) / "workflow_storage"
            self.psop_dir = base / "psop"
            self.preflow_dir = base / "preflow"
            self.execution_dir = base / "execution_records"

        self._init_storage()

    def save_psop(self, psop: PSOP) -> str:
        """
        Save PSOP to storage (always to zh/ canonical directory).

        Args:
            psop: PSOP object to save

        Returns:
            str: PSOP ID

        Raises:
            WorkflowStorageError: If save fails
        """
        try:
            file_path = self._get_save_path(psop.id, "psop")
            self._atomic_write(file_path, psop.model_dump_json(indent=2))
            logger.info(f"PSOP saved: {psop.id} at {file_path}")
            return psop.id
        except Exception as e:
            logger.error(f"Failed to save PSOP: {e}")
            raise WorkflowStorageError(f"Failed to save PSOP: {e}")

    def save_preflow(self, preflow: PreFlow) -> str:
        """
        Save PreFlow to storage.

        Args:
            preflow: PreFlow object to save

        Returns:
            str: PreFlow ID

        Raises:
            WorkflowStorageError: If save fails
        """
        try:
            file_path = self._get_save_path(preflow.id, "preflow")
            self._atomic_write(file_path, preflow.model_dump_json(indent=2))
            logger.info(f"PreFlow saved : {preflow.id} at {file_path}")
            return preflow.id
        except Exception as e:
            logger.error(f"Failed to save PreFlow: {e}")
            raise WorkflowStorageError(f"Failed to save PreFlow: {e}") from e

    def load_psop(self, workflow_id: str) -> Optional[PSOP]:
        """
        Load PSOP from storage. Tries lang-specific directory first, falls back to zh/.

        Args:
            workflow_id: PSOP ID

        Returns:
            Optional[PSOP]: PSOP object if found, None otherwise
        """
        try:
            file_path = self._get_file_path(workflow_id, "psop")
            if not file_path.exists():
                logger.warning(f"PSOP not found : {workflow_id}")
                return None
            with open(file_path, "r", encoding='utf-8') as f:
                return PSOP.model_validate_json(f.read())
        except Exception as e:
            logger.error(f"Failed to load PSOP {workflow_id} : {e}")
            return None

    def load_preflow(self, workflow_id: str) -> Optional[PreFlow]:
        """
        Load PreFlow from storage.

        Args:
            workflow_id: PreFlow ID

        Returns:
            Optional[PreFlow]: PreFlow object if found, None otherwise
        """
        try:
            file_path = self._get_file_path(workflow_id, "preflow")
            if not file_path.exists():
                logger.warning(f"PreFlow not found : {workflow_id}")
                return None
            with open(file_path, "r", encoding='utf-8') as f:
                return PreFlow.model_validate_json(f.read())
        except Exception as e:
            logger.error(f"Failed to load PreFlow {workflow_id} : {e}")
            return None

    def delete_psop(self, workflow_id: str) -> bool:
        """
        Delete PSOP from storage.

        Args:
            workflow_id: PSOP ID

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            file_path = self._get_file_path(workflow_id, "psop")
            if file_path.exists():
                file_path.unlink()
                logger.info(f"PSOP deleted : {workflow_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete PSOP {workflow_id} : {e}")
            return False

    def delete_preflow(self, workflow_id: str) -> bool:
        """
        Delete PreFlow from storage.

        Args:
            workflow_id: PreFlow ID

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            file_path = self._get_file_path(workflow_id, "preflow")
            if file_path.exists():
                file_path.unlink()
                logger.info(f"PreFlow deleted : {workflow_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete PreFlow {workflow_id} : {e}")
            return False

    def list_psops(self) -> List[str]:
        """
        List all PSOP IDs in storage.

        Returns:
            List[str]: List of PSOP IDs (from JSON content, not filenames)
        """
        ids = []
        for f in self.psop_dir.glob("*.json"):
            try:
                with open(f, "r", encoding='utf-8') as fh:
                    data = json.loads(fh.read())
                    internal_id = data.get("id")
                    if internal_id:
                        ids.append(internal_id)
                    else:
                        ids.append(f.stem)
            except Exception:
                ids.append(f.stem)
        return ids

    def list_preflows(self) -> List[str]:
        """
        List all PreFlow IDs in storage.

        Returns:
            List[str]: List of PreFlow IDs (from JSON content, not filenames)
        """
        ids = []
        for f in self.preflow_dir.glob("*.json"):
            try:
                with open(f, "r", encoding='utf-8') as fh:
                    data = json.loads(fh.read())
                    internal_id = data.get("id")
                    if internal_id:
                        ids.append(internal_id)
                    else:
                        ids.append(f.stem)
            except Exception:
                ids.append(f.stem)
        return ids

    def update_psop(self, psop: PSOP) -> bool:
        """
        Update existing PSOP in storage.

        Args:
            psop: PSOP object to update

        Returns:
            bool: True if updated, False if PSOP not found
        """
        file_path = self._get_file_path(psop.id, "psop")
        if not file_path.exists():
            logger.warning(f"PSOP not found for update : {psop.id}")
            return False
        self.save_psop(psop)
        return True

    def update_preflow(self, preflow: PreFlow) -> bool:
        """
        Update existing PreFlow in storage.

        Args:
            preflow: PreFlow object to update

        Returns:
            bool: True if updated, False if PreFlow not found
        """
        file_path = self._get_file_path(preflow.id, "preflow")
        if not file_path.exists():
            logger.warning(f"Preflow not found for update : {preflow.id}")
            return False
        self.save_preflow(preflow)
        return True

    def save_execution_record(self, record: ExecutionRecord) -> str:
        """
        Save execution record to storage.

        Args:
            record: ExecutionRecord object to save

        Returns:
            str: Execution record ID
        """
        try:
            file_path = self.execution_dir / f"{record.execution_id}.json"
            self._atomic_write(file_path, record.model_dump_json(indent=2))
            logger.info(f"Execution record saved: {record.execution_id} @ {file_path}")
            return record.execution_id
        except Exception as e:
            logger.error(f"Failed to save execution record: {e}")
            raise WorkflowStorageError(f"Failed to save execution record: {e}")

    def load_execution_record(self, execution_id: str) -> Optional[ExecutionRecord]:
        """
        Load execution record from storage.

        Args:
            execution_id: Execution record ID

        Returns:
            Optional[ExecutionRecord]: ExecutionRecord object if found, None otherwise
        """
        try:
            file_path = self.execution_dir / f"{execution_id}.json"
            if not file_path.exists():
                return None
            with open(file_path, "r", encoding='utf-8') as f:
                return ExecutionRecord.model_validate_json(f.read())
        except Exception as e:
            logger.error(f"Failed to load execution record {execution_id}: {e}")
            return None

    def list_execution_records(self) -> List[Dict[str, Any]]:
        """
        List all execution records (summary only, no full events).

        Returns:
            List[Dict]: List of execution record summaries sorted by started_at desc
        """
        records = []
        for f in sorted(self.execution_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(f, "r", encoding='utf-8') as fh:
                    record = ExecutionRecord.model_validate_json(fh.read())
                    records.append({
                        "execution_id": record.execution_id,
                        "psop_id": record.psop_id,
                        "psop_name": record.psop_name,
                        "started_at": record.started_at.isoformat() if record.started_at else None,
                        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                        "status": record.status,
                        "step_count": len(record.execution_history),
                        "error": record.error,
                    })
            except Exception as e:
                logger.error(f"Failed to read execution record {f.stem}: {e}")
        return records

    def delete_execution_record(self, execution_id: str) -> bool:
        """
        Delete execution record from storage.

        Args:
            execution_id: Execution record ID

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            file_path = self.execution_dir / f"{execution_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Execution record deleted: {execution_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete execution record {execution_id}: {e}")
            return False

    def _init_storage(self) -> None:
        self.psop_dir.mkdir(parents=True, exist_ok=True)
        self.preflow_dir.mkdir(parents=True, exist_ok=True)
        self.execution_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Storage initialized at: psop={self.psop_dir}, preflow={self.preflow_dir}, execution={self.execution_dir}")

    def _get_save_path(self, workflow_id: str, workflow_type: str) -> Path:
        if not re.match(r'^[\w\-]+$', workflow_id):
            raise WorkflowStorageError(f"Invalid workflow_id: {workflow_id}")
        if workflow_type == "psop":
            return self.psop_dir / f"{workflow_id}.json"
        elif workflow_type == "preflow":
            return self.preflow_dir / f"{workflow_id}.json"
        else:
            raise WorkflowStorageError(f"Unknown workflow type: {workflow_type}")

    def _get_file_path(self, workflow_id: str, workflow_type: str) -> Path:
        """
        Get file path for workflow storage.

        Args:
            workflow_id: Workflow ID
            workflow_type: 'psop' or 'preflow'

        Returns:
            Path: File path

        Raises:
            WorkflowStorageError: If workflow type is unknown or workflow_id is invalid
        """
        if not re.match(r'^[\w\-]+$', workflow_id):
            raise WorkflowStorageError(f"Invalid workflow_id: {workflow_id}")
        if workflow_type == "psop":
            return self.psop_dir / f"{workflow_id}.json"
        elif workflow_type == "preflow":
            return self.preflow_dir / f"{workflow_id}.json"
        else:
            raise WorkflowStorageError(f"Unknown workflow type : {workflow_type}")

    @staticmethod
    def _atomic_write(file_path: Path, content: str) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=file_path.parent, suffix='.tmp')
        try:
            os.write(tmp_fd, content.encode('utf-8'))
        finally:
            os.close(tmp_fd)
        os.replace(tmp_path, file_path)
