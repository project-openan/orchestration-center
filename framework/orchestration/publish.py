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
    pass


class PublishedWorkflow:

    def __init__(self, workflow_id: str, workflow_type: str, name: str,
                 version: str, status: PublishStatus, published_at: Optional[datetime],
                 published_by: Optional[str], description: Optional[str] = None):
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.name = name
        self.version = version
        self.status = status
        self.published_at = published_at
        self.published_by = published_by
        self.description = description

    def to_dict(self):
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
    def __init__(self, storage: WorkflowStorage):
        self.storage = storage
        self._published_registry: dict = {}
        self._version_registry: dict = {}

    def publish_psop(self, psop: PSOP, version: str = "1.0.0",
                     published_by: Optional[str] = None) -> PublishedWorkflow:
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
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id and pwf.workflow_type == workflow_type:
                    pwf.status = PublishStatus.DEPRECATED
                    logger.info(f"Workflow deprecated : {workflow_id}")
                    return True
        logger.warning(f"Workflow not found for deprecation : {workflow_id}")
        return False

    def archive_workflow(self, workflow_id: str, workflow_type: str) -> bool:
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id and pwf.workflow_type == workflow_type:
                    pwf.status = PublishStatus.ARCHIVED
                    logger.info(f"Workflow archived : {workflow_id}")
                    return True
        logger.warning(f"Workflow not found for archiving : {workflow_id}")
        return False

    def get_published_versions(self, name: str, workflow_type: str) -> List[PublishedWorkflow]:
        registry_key = f"{workflow_type}:{name}"
        return self._published_registry.get(registry_key, [])

    def get_latest_version(self, name: str, workflow_type: str) -> Optional[PublishedWorkflow]:
        versions = self.get_published_versions(name, workflow_type)
        if not versions:
            return None
        return max(versions, key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc))

    def list_published(self, status: Optional[PublishStatus] = None,
                       workflow_type: Optional[str] = None) -> List[PublishedWorkflow]:
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
        for _, versions in self._published_registry.items():
            for pwf in versions:
                if pwf.workflow_id == workflow_id:
                    return True
        return False
