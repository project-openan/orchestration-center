import logging
from pathlib import Path
from typing import Optional, List

from orchestration.model.preflow import PreFlow
from orchestration.model.psop import PSOP

logger = logging.getLogger(__name__)


class WorkflowStorageError(Exception):
    pass


class WorkflowStorage:
    def __init__(self, storage_dir: str = "./workflow_storage"):
        self.storage_dir = Path(storage_dir)
        self.psop_dir = self.storage_dir / "psop"
        self.preflow_dir = self.storage_dir / "preflow"
        self._init_storage()

    def save_psop(self, psop: PSOP) -> str:
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
        return [f.stem for f in self.psop_dir.glob("*.json")]

    def list_preflows(self) -> List[str]:
        return [f.stem for f in self.preflow_dir.glob("*.json")]

    def update_psop(self, psop: PSOP) -> bool:
        file_path = self._get_file_path(psop.id, "psop")
        if not file_path.exists():
            logger.warning(f"PSOP not found for update : {psop.id}")
            return False
        self.save_psop(psop)
        return True

    def update_preflow(self, preflow: PreFlow) -> bool:
        file_path = self._get_file_path(preflow.id, "preflow")
        if not file_path.exists():
            logger.warning(f"Preflow not found for update : {preflow.id}")
            return False
        self.save_preflow(preflow)
        return True

    def _init_storage(self) -> None:
        self.psop_dir.mkdir(parents=True, exist_ok=True)
        self.preflow_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workflow storage initialized at : {self.storage_dir}")

    def _get_file_path(self, workflow_id: str, workflow_type: str) -> Path:
        if workflow_type == "psop":
            return self.psop_dir / f"{workflow_id}.json"
        elif workflow_type == "preflow":
            return self.preflow_dir / f"{workflow_id}.json"
        else:
            raise WorkflowStorageError(f"Unknown workflow type : {workflow_type}")
