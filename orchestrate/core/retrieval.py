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

import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from common.llm import get_llm_instance
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.prompts import get_retrieve_psop_prompt


class WorkflowSearchResult:
    def __init__(self, workflow_id: str, workflow_type: str, name: str,
                 description: Optional[str], tags: Optional[List[str]],
                 created_at: datetime, score: float = 1.0):
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.name = name
        self.description = description
        self.tags = tags or []
        self.created_at = created_at
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
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
    def __init__(self, storage: WorkflowStorage):
        self.storage = storage

    def get_psop_by_id(self, workflow_id: str) -> Optional[PSOP]:
        return self.storage.load_psop(workflow_id)

    def get_preflow_by_id(self, workflow_id: str) -> Optional[PreFlow]:
        return self.storage.load_preflow(workflow_id)

    def search_by_name(self, name_pattern: str, workflow_type: str = "all") -> List[WorkflowSearchResult]:
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
        if workflow_type in ("all", "preflow"):
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
        results = []
        for wf_id in self.storage.list_preflows():
            psop = self.storage.load_psop(wf_id)
            if psop and psop.related_preflow == preflow_id:
                results.append(psop)
        return results

    def list_recent_workflows(self, limit: int = 10, workflow_type: str = "all") -> List[WorkflowSearchResult]:
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

    def _parse_json_response(self, llm_response: str) -> str:
        """Parse JSON response from LLM output.
        
        Extracts JSON from code blocks in LLM responses.
        
        Args:
            llm_response: Raw LLM response string containing JSON code blocks
            
        Returns:
            Parsed string value from JSON
            
        Raises:
            ValueError: If no JSON code block found, empty content, or invalid JSON
        """
        matches = re.findall(r'```json(.*?)```', llm_response, re.DOTALL)
        if not matches:
            raise ValueError("No JSON code block found in LLM answer")

        json_str = matches[-1].strip()
        if not json_str:
            raise ValueError("Empty JSON content found in code block")

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    def retrieve_psop_by_intent(self, user_intent: str) -> Optional[PSOP]:
        """Retrieve the most suitable PSOP based on user's natural language intent.
        
        Uses LLM to analyze user intent and select the most appropriate PSOP
        from all available PSOPs based on their names and descriptions.
        
        Args:
            user_intent: Natural language description of user's intent
            
        Returns:
            The most suitable PSOP object, or None if no suitable PSOP found
            
        Raises:
            Exception: If LLM API call fails or parsing fails
        """
        # 获取所有PSOP数据
        psop_list = []
        for wf_id in self.storage.list_psops():
            psop = self.storage.load_psop(wf_id)
            if psop:
                psop_list.append({
                    "name": psop.name,
                    "user_intent": psop.user_intent or "",
                    "id": psop.id
                })
        
        if not psop_list:
            return None
            
        # 准备PSOP列表字符串
        psop_list_str = json.dumps(psop_list, ensure_ascii=False, indent=2)
        
        # 获取LLM实例并调用
        llm = get_llm_instance()
        prompt = get_retrieve_psop_prompt(user_intent, psop_list_str)
        
        try:
            _, llm_res = llm.ask_llm(prompt)
            selected_psop_name = self._parse_json_response(llm_res)
            
            # 如果LLM返回空字符串，表示没有找到合适的PSOP
            if not selected_psop_name:
                return None
                
            # 根据选择的PSOP名称查找对应的PSOP对象
            for psop_info in psop_list:
                if psop_info["name"] == selected_psop_name:
                    return self.storage.load_psop(psop_info["id"])
                    
            return None
            
        except Exception as e:
            raise Exception(f"Failed to retrieve PSOP by intent: {e}")
