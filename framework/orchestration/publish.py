from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from loguru import logger

from framework.orchestration.model.preflow import PreFlow
from framework.orchestration.model.psop import PSOP
from framework.orchestration.persistence import WorkflowStorage


class PublishStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class WorkflowPublishError(Exception):
    """Workflow publishing exception.
    
    Raised when workflow publishing operation fails, such as storage failure, version conflict, etc.
    """
    pass


class PublishedWorkflow:
    """Published workflow.
    
    Represents a published workflow version, containing version information, status, and publishing metadata.
    
    Attributes:
        workflow_id: Workflow ID
        workflow_type: Workflow type ("psop" or "preflow")
        name: Workflow name
        version: Version number
        status: Publication status
        published_at: Publication timestamp
        published_by: Publisher identity
        description: Workflow description
    """

    def __init__(self, workflow_id: str, workflow_type: str, name: str,
                 version: str, status: PublishStatus, published_at: Optional[datetime],
                 published_by: Optional[str], description: Optional[str] = None):
        """Initialize a published workflow.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: Workflow type ("psop" or "preflow")
            name: Workflow name
            version: Version number
            status: Publication status
            published_at: Publication timestamp
            published_by: Publisher identity
            description: Workflow description
        """
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.name = name
        self.version = version
        self.status = status
        self.published_at = published_at
        self.published_by = published_by
        self.description = description

    def to_dict(self):
        """Convert the published workflow to dictionary format.
        
        Returns:
            Dictionary containing all fields of the published workflow
        """
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_by": self.published_by,
            "description": self.description
        }


class WorkflowPublisher:
    """Workflow publishing manager.
    
    Manages workflow publishing, version control, and status management.
    Supports publishing of both PSOP and PreFlow workflow types.
    
    Attributes:
        storage: Workflow storage manager instance
        _published_registry: Published workflow registry
        _version_registry: Version registry
    """
    def __init__(self, storage: WorkflowStorage):
        """Initialize workflow publishing manager.
        
        Args:
            storage: Workflow storage manager instance
        """
        self.storage = storage
        self._published_registry: dict = {}
        self._version_registry: dict = {}

    def publish_psop(self, psop: PSOP, version: str = "1.0.0",
                     published_by: Optional[str] = None) -> PublishedWorkflow:
        """Publish a PSOP workflow.
        
        Args:
            psop: PSOP workflow object
            version: Version number, defaults to "1.0.0"
            published_by: Publisher identity
            
        Returns:
            Published workflow object
            
        Raises:
            WorkflowPublishError: Raised when publishing fails
        """
        try:
            workflow_id = self.storage.save_psop(psop)
            published_wf = PublishedWorkflow(
                workflow_id=workflow_id,
                workflow_type="psop",
                name=psop.name,
                version=version,
                status=PublishStatus.PUBLISHED,
                published_at=datetime.now(tz=timezone.utc),
                published_by=published_by,
                description=psop.description
            )
            registry_key = f"psop:{psop.name}"
            if registry_key not in self._published_registry:
                self._published_registry[registry_key] = []
            self._published_registry[registry_key].append(published_wf)
            self._version_registry[workflow_id] = version

            logger.info(f"PSOP published : {psop.name} v{version} by {published_by}")
            return published_wf
        except Exception as e:
            logger.error(f"Failed to publish PSOP : {e}")
            raise WorkflowPublishError(f"Failed to publish PSOP : {e}") from e

    def publish_preflow(self, preflow: PreFlow, version: str = "1.0.0",
                        published_by: Optional[str] = None) -> PublishedWorkflow:
        """Publish a PreFlow workflow.
        
        Args:
            preflow: PreFlow workflow object
            version: Version number, defaults to "1.0.0"
            published_by: Publisher identity
            
        Returns:
            Published workflow object
            
        Raises:
            WorkflowPublishError: Raised when publishing fails
        """
        try:
            workflow_id = self.storage.save_preflow(preflow)
            published_wf = PublishedWorkflow(
                workflow_id=workflow_id,
                workflow_type="preflow",
                name=preflow.name,
                version=version,
                status=PublishStatus.PUBLISHED,
                published_at=datetime.now(tz=timezone.utc),
                published_by=published_by,
                description=preflow.description
            )
            registry_key = f"preflow:{preflow.name}"
            if registry_key not in self._published_registry:
                self._published_registry[registry_key] = []
            self._published_registry[registry_key].append(published_wf)
            self._version_registry[workflow_id] = version
            logger.info(f"PreFlow published : {preflow.name} v{version} by {published_by}")
            return published_wf
        except Exception as e:
            logger.error(f"Failed to publish PreFlow : {e}")
            raise WorkflowPublishError(f"Failed to publish PreFlow : {e}") from e

    def deprecate_workflow(self, workflow_id: str, workflow_type: str) -> bool:
        """Deprecate a workflow.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: Workflow type
            
        Returns:
            True if successfully deprecated, False otherwise
        """
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id and pwf.workflow_type == workflow_type:
                    pwf.status = PublishStatus.DEPRECATED
                    logger.info(f"Workflow deprecated : {workflow_id}")
                    return True
        logger.warning(f"Workflow not found for deprecation : {workflow_id}")
        return False

    def archive_workflow(self, workflow_id: str, workflow_type: str) -> bool:
        """Archive a workflow.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: Workflow type
            
        Returns:
            True if successfully archived, False otherwise
        """
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id and pwf.workflow_type == workflow_type:
                    pwf.status = PublishStatus.ARCHIVED
                    logger.info(f"Workflow archived : {workflow_id}")
                    return True
        logger.warning(f"Workflow not found for archiving : {workflow_id}")
        return False

    def get_published_versions(self, name: str, workflow_type: str) -> List[PublishedWorkflow]:
        """Get all published versions of a workflow.
        
        Args:
            name: Workflow name
            workflow_type: Workflow type ("psop" or "preflow")
            
        Returns:
            List of published workflow versions
        """
        registry_key = f"{workflow_type}:{name}"
        return self._published_registry.get(registry_key, [])

    def get_latest_version(self, name: str, workflow_type: str) -> Optional[PublishedWorkflow]:
        """Get the latest published version of a workflow.
        
        Args:
            name: Workflow name
            workflow_type: Workflow type ("psop" or "preflow")
            
        Returns:
            Latest published workflow version, or None if no versions exist
        """
        versions = self.get_published_versions(name, workflow_type)
        if not versions:
            return None
        return max(versions, key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc))

    def list_published(self, status: Optional[PublishStatus] = None,
                       workflow_type: Optional[str] = None) -> List[PublishedWorkflow]:
        """List published workflows with optional filters.
        
        Args:
            status: Filter by publication status (e.g., PUBLISHED, DRAFT)
            workflow_type: Filter by workflow type ("psop" or "preflow")
            
        Returns:
            List of published workflows matching the filters
        """
        results = []
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if status and pwf.status != status:
                    continue
                if workflow_type and pwf.workflow_type != workflow_type:
                    continue
                results.append(pwf)
        return results

    def is_published(self, workflow_id: str) -> bool:
        """Check if a workflow is published.
        
        Args:
            workflow_id: Workflow ID to check
            
        Returns:
            True if the workflow is published, False otherwise
        """
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id:
                    return True
        return False
