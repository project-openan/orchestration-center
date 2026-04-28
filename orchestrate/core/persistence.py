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

from loguru import logger
from pathlib import Path
from typing import Optional, List

from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP

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
        else:
            self.psop_dir = Path(storage_dir) / "workflow_storage" / "psop"
            self.preflow_dir = Path(storage_dir) / "workflow_storage" / "preflow"
        self._init_storage()

    def save_psop(self, psop: PSOP) -> str:
        """
        Save PSOP to storage.
        
        Args:
            psop: PSOP object to save
            
        Returns:
            str: PSOP ID
            
        Raises:
            WorkflowStorageError: If save fails
        """
        try:
            file_path = self._get_file_path(psop.id, "psop")
            with open(file_path, "w", encoding='utf-8') as f:
                f.write(psop.model_dump_json(indent=2))
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
            file_path = self._get_file_path(preflow.id, "preflow")
            with open(file_path, "w", encoding='utf-8') as f:
                f.write(preflow.model_dump_json(indent=2))
            logger.info(f"PreFlow saved : {preflow.id} at {file_path}")
            return preflow.id
        except Exception as e:
            logger.error(f"Failed to save PreFlow: {e}")
            raise WorkflowStorageError(f"Failed to save PreFlow: {e}") from e

    def load_psop(self, workflow_id: str) -> Optional[PSOP]:
        """
        Load PSOP from storage.
        
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
            List[str]: List of PSOP IDs
        """
        return [f.stem for f in self.psop_dir.glob("*.json")]

    def list_preflows(self) -> List[str]:
        """
        List all PreFlow IDs in storage.
        
        Returns:
            List[str]: List of PreFlow IDs
        """
        return [f.stem for f in self.preflow_dir.glob("*.json")]

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

    def _init_storage(self) -> None:
        """
        Initialize storage directories.
        """
        self.psop_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"PSOP storage initialized at : {self.psop_dir}")
        self.preflow_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Preflow storage initialized at : {self.preflow_dir}")

    def _get_file_path(self, workflow_id: str, workflow_type: str) -> Path:
        """
        Get file path for workflow storage.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: 'psop' or 'preflow'
            
        Returns:
            Path: File path
            
        Raises:
            WorkflowStorageError: If workflow type is unknown
        """
        if workflow_type == "psop":
            return self.psop_dir / f"{workflow_id}.json"
        elif workflow_type == "preflow":
            return self.preflow_dir / f"{workflow_id}.json"
        else:
            raise WorkflowStorageError(f"Unknown workflow type : {workflow_type}")
