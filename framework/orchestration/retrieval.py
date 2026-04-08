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
from typing import Optional, List, Dict, Any

from framework.orchestration.model.preflow import PreFlow
from framework.orchestration.model.psop import PSOP
from framework.orchestration.persistence import WorkflowStorage


class WorkflowSearchResult:
    """Workflow search result.
    
    Represents the result of a workflow search query, containing basic workflow information and match score.
    
    Attributes:
        workflow_id: Workflow ID
        workflow_type: Workflow type ("psop" or "preflow")
        name: Workflow name
        description: Workflow description
        tags: Workflow tags list
        created_at: Creation timestamp
        score: Match score, default 1.0
    """
    def __init__(self, workflow_id: str, workflow_type: str, name: str,
                 description: Optional[str], tags: Optional[List[str]],
                 created_at: datetime, score: float = 1.0):
        """Initialize workflow search result.
        
        Args:
            workflow_id: Workflow ID
            workflow_type: Workflow type ("psop" or "preflow")
            name: Workflow name
            description: Workflow description
            tags: Workflow tags list
            created_at: Creation timestamp
            score: Match score, default 1.0
        """
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.name = name
        self.description = description
        self.tags = tags or []
        self.created_at = created_at
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        """Convert search result to dictionary format.
        
        Returns:
            Dictionary containing all fields of the search result
        """
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "score": self.score
        }


class WorkflowRetrieval:
    """Workflow retrieval manager.
    
    Provides various workflow retrieval functionalities, including search by ID, name, tags, description, etc.
    Supports retrieval of both PSOP and PreFlow workflow types.
    
    Attributes:
        storage: Workflow storage manager instance
    """
    def __init__(self, storage: WorkflowStorage):
        """Initialize workflow retrieval manager.
        
        Args:
            storage: Workflow storage manager instance
        """
        self.storage = storage

    def get_psop_by_id(self, workflow_id: str) -> Optional[PSOP]:
        """Get PSOP workflow by ID.
        
        Args:
            workflow_id: PSOP workflow ID
            
        Returns:
            PSOP workflow object, or None if not found
        """
        return self.storage.load_psop(workflow_id)

    def get_preflow_by_id(self, workflow_id: str) -> Optional[PreFlow]:
        """Get PreFlow workflow by ID.
        
        Args:
            workflow_id: PreFlow workflow ID
            
        Returns:
            PreFlow workflow object, or None if not found
        """
        return self.storage.load_preflow(workflow_id)

    def search_by_name(self, name_pattern: str, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        """Search workflows by name pattern.
        
        Args:
            name_pattern: Name pattern (case-insensitive)
            workflow_type: Workflow type, optional values: "all", "psop", "preflow"
            
        Returns:
            List of matching workflow search results
        """
        results = []
        name_lower = name_pattern.lower()
        if workflow_type in ("all", "psop"):
            for wf_id in self.storage.list_psops():
                psop = self.storage.load_psop(wf_id)
                if psop and name_lower in psop.name.lower():
                    results.append(WorkflowSearchResult(
                        workflow_id=psop.id,
                        workflow_type="psop",
                        name=psop.name,
                        description=psop.description,
                        tags=psop.tags,
                        created_at=psop.created_at
                    ))
        if workflow_type in ("all", "psop"):
            for wf_id in self.storage.list_preflows():
                preflow = self.storage.load_preflow(wf_id)
                if preflow and name_lower in preflow.name.lower():
                    results.append(WorkflowSearchResult(
                        workflow_id=preflow.id,
                        workflow_type="preflow",
                        name=preflow.name,
                        description=preflow.description,
                        tags=preflow.tags,
                        created_at=preflow.created_at
                    ))
        return results

    def search_by_tags(self, tags: List[str], match_all: bool = False, workflow_type: str = "all") -> List[
        WorkflowSearchResult]:
        """Search workflows by tags.
        
        Args:
            tags: List of tags
            match_all: Whether to match all tags (True) or any tag (False)
            workflow_type: Workflow type, optional values: "all", "psop", "preflow"
            
        Returns:
            List of matching workflow search results
        """
        results = []
        search_tags_lower = [t.lower() for t in tags]

        def matches_tags(workflow_tags: Optional[List[str]]) -> bool:
            if not workflow_tags:
                return False
            workflow_tags_lower = [t.lower() for t in workflow_tags]
            if match_all:
                return all(st in workflow_tags_lower for st in search_tags_lower)
            else:
                return any(st in workflow_tags_lower for st in search_tags_lower)

        if workflow_type in ("all", "psop"):
            for wf_id in self.storage.list_psops():
                psop = self.storage.load_psop(wf_id)
                if psop and matches_tags(psop.tags):
                    results.append(WorkflowSearchResult(
                        workflow_id=psop.id,
                        workflow_type="psop",
                        name=psop.name,
                        description=psop.description,
                        tags=psop.tags,
                        created_at=psop.created_at
                    ))
        if workflow_type in ("all", "preflow"):
            for wf_id in self.storage.list_preflows():
                preflow = self.storage.load_preflow(wf_id)
                if preflow and matches_tags(preflow.tags):
                    results.append(WorkflowSearchResult(
                        workflow_id=preflow.id,
                        workflow_type="preflow",
                        name=preflow.name,
                        description=preflow.description,
                        tags=preflow.tags,
                        created_at=preflow.created_at
                    ))
        return results

    def search_by_description(self, keyword: str, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        """Search workflows by description keyword.
        
        Args:
            keyword: Keyword (case-insensitive)
            workflow_type: Workflow type, optional values: "all", "psop", "preflow"
            
        Returns:
            List of matching workflow search results
        """
        results = []
        keyword_lower = keyword.lower()
        if workflow_type in ("all", "psop"):
            for wf_id in self.storage.list_psops():
                psop = self.storage.load_psop(wf_id)
                if psop and psop.description and keyword_lower in psop.description.lower():
                    results.append(WorkflowSearchResult(
                        workflow_id=psop.id,
                        workflow_type="psop",
                        name=psop.name,
                        description=psop.description,
                        tags=psop.tags,
                        created_at=psop.created_at
                    ))
        if workflow_type in ("all", "preflow"):
            for wf_id in self.storage.list_preflows():
                preflow = self.storage.load_preflow(wf_id)
                if preflow and preflow.description and keyword_lower in preflow.description.lower():
                    results.append(WorkflowSearchResult(
                        workflow_id=preflow.id,
                        workflow_type="preflow",
                        name=preflow.name,
                        description=preflow.description,
                        tags=preflow.tags,
                        created_at=preflow.created_at
                    ))
        return results

    def get_psop_by_preflow(self, preflow_id: str) -> List[PSOP]:
        """Get related PSOP workflows by PreFlow ID.
        
        Args:
            preflow_id: PreFlow workflow ID
            
        Returns:
            List of related PSOP workflows
        """
        results = []
        for wf_id in self.storage.list_preflows():
            psop = self.storage.load_psop(wf_id)
            if psop and psop.related_preflow == preflow_id:
                results.append(psop)
        return results

    def list_recent_workflows(self, limit: int = 10, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        """List recent workflows.
        
        Args:
            limit: Maximum number of results to return
            workflow_type: Workflow type, optional values: "all", "psop", "preflow"
            
        Returns:
            List of recent workflow search results, sorted by creation time descending
        """
        results = []
        if workflow_type in ("all", "psop"):
            for wf_id in self.storage.list_psops():
                psop = self.storage.load_psop(wf_id)
                if psop:
                    results.append(WorkflowSearchResult(
                        workflow_id=psop.id,
                        workflow_type="psop",
                        name=psop.name,
                        description=psop.description,
                        tags=psop.tags,
                        created_at=psop.created_at
                    ))
        if workflow_type in ("all", "preflow"):
            for wf_id in self.storage.list_preflows():
                preflow = self.storage.load_preflow(wf_id)
                if preflow:
                    results.append(WorkflowSearchResult(
                        workflow_id=preflow.id,
                        workflow_type="preflow",
                        name=preflow.name,
                        description=preflow.description,
                        tags=preflow.tags,
                        created_at=preflow.created_at
                    ))
        # 使用timestamp进行排序，避免offset-naive和offset-aware datetime比较错误
        results.sort(key=lambda x: x.created_at.timestamp() if x.created_at.tzinfo else x.created_at.replace(tzinfo=timezone.utc).timestamp(), reverse=True)
        return results[:limit]
