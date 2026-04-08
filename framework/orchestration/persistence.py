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

from framework.orchestration.model.preflow import PreFlow
from framework.orchestration.model.psop import PSOP

class WorkflowStorageError(Exception):
    """Workflow storage exception.
    
    Raised when workflow storage operations fail, such as file I/O errors, data validation failures, etc.
    """
    pass


class WorkflowStorage:
    """Workflow storage manager.
    
    Responsible for persistent storage of PSOP and PreFlow workflows, including save, load, delete, and list operations.
    Workflows are stored in JSON format in the local file system.
    
    Attributes:
        storage_dir: Storage root directory
        psop_dir: PSOP workflow storage directory
        preflow_dir: PreFlow workflow storage directory
    """
    def __init__(self, storage_dir: str = "./workflow_storage"):
        """Initialize workflow storage manager.
        
        Args:
            storage_dir: Storage directory path, defaults to "./workflow_storage"
        """
        self.storage_dir = Path(storage_dir)
        self.psop_dir = self.storage_dir / "psop"
        self.preflow_dir = self.storage_dir / "preflow"
        self._init_storage()

    def save_psop(self, psop: PSOP) -> str:
        """Save PSOP workflow to storage system.
        
        Args:
            psop: PSOP workflow object
            
        Returns:
            Saved workflow ID
            
        Raises:
            WorkflowStorageError: Raised when save fails
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
        """Save PreFlow workflow to storage system.
        
        Args:
            preflow: PreFlow workflow object
            
        Returns:
            Saved workflow ID
            
        Raises:
            WorkflowStorageError: Raised when save fails
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
        """Load PSOP workflow from storage system.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            PSOP workflow object, or None if not found
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
        """Load PreFlow workflow from storage system.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            PreFlow workflow object, or None if not found
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
        """Delete PSOP workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            True if successfully deleted, False otherwise
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
        """Delete PreFlow workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            True if successfully deleted, False otherwise
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
        """List all PSOP workflow IDs.
        
        Returns:
            List of PSOP workflow IDs
        """
        return [f.stem for f in self.psop_dir.glob("*.json")]

    def list_preflows(self) -> List[str]:
        """List all PreFlow workflow IDs.
        
        Returns:
            List of PreFlow workflow IDs
        """
        return [f.stem for f in self.preflow_dir.glob("*.json")]

    def update_psop(self, psop: PSOP) -> bool:
        """Update PSOP workflow.
        
        Args:
            psop: Updated PSOP workflow object
            
        Returns:
            True if successfully updated, False otherwise
        """
        file_path = self._get_file_path(psop.id, "psop")
        if not file_path.exists():
            logger.warning(f"PSOP not found for update : {psop.id}")
            return False
        self.save_psop(psop)
        return True

    def update_preflow(self, preflow: PreFlow) -> bool:
        """Update PreFlow workflow.
        
        Args:
            preflow: Updated PreFlow workflow object
            
        Returns:
            True if successfully updated, False otherwise
        """
        file_path = self._get_file_path(preflow.id, "preflow")
        if not file_path.exists():
            logger.warning(f"Preflow not found for update : {preflow.id}")
            return False
        self.save_preflow(preflow)
        return True

    def _init_storage(self) -> None:
        """Initialize storage directories.
        
        Create PSOP and PreFlow storage directories if they don't exist.
        """
        self.psop_dir.mkdir(parents=True, exist_ok=True)
        self.preflow_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workflow storage initialized at : {self.storage_dir}")

    def _get_file_path(self, workflow_id: str, workflow_type: str) -> Path:
        """Get storage file path for a workflow.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: Workflow type ("psop" or "preflow")
            
        Returns:
            Workflow file path
            
        Raises:
            WorkflowStorageError: Raised when workflow type is unknown
        """
        if workflow_type == "psop":
            return self.psop_dir / f"{workflow_id}.json"
        elif workflow_type == "preflow":
            return self.preflow_dir / f"{workflow_id}.json"
        else:
            raise WorkflowStorageError(f"Unknown workflow type : {workflow_type}")
