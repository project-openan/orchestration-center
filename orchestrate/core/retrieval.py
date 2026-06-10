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
from datetime import timezone
from typing import Optional, List

from loguru import logger

from common.custom import HandlerRegistry, InterfaceType
from common.custom.psop_processor import build_tasks_summary
from common.llm import get_llm_instance
from common.util.config_util import get_conf
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.prompts import get_retrieve_psop_prompt
from orchestrate.core.workflow_search_result import WorkflowSearchResult


class WorkflowRetrieval:
    def __init__(self, storage: WorkflowStorage):
        self.storage = storage
        self._db_mode = get_conf().get("persistence_mode", "file").lower() != "file"

    def _list_psop_summaries(self) -> List[WorkflowSearchResult]:
        if self._db_mode:
            return HandlerRegistry.get_handler(InterfaceType.GET_ALL_PSOP).handle()
        results = []
        for wf_id in self.storage.list_psops():
            psop = self.storage.load_psop(wf_id)
            if psop:
                tasks_summary = build_tasks_summary(psop)
                results.append(WorkflowSearchResult(
                    workflow_id=psop.id,
                    workflow_type="psop",
                    name=psop.name,
                    description=psop.description,
                    tags=psop.tags,
                    created_at=psop.created_at,
                    user_intent=psop.user_intent,
                    related_preflow=psop.related_preflow,
                    tasks_summary=tasks_summary,
                ))
        return results

    def _load_psop_by_id(self, workflow_id: str) -> Optional[PSOP]:
        if self._db_mode:
            return HandlerRegistry.get_handler(InterfaceType.GET_PSOP_BY_ID).handle(workflow_id)
        return self.storage.load_psop(workflow_id)

    def get_psop_by_id(self, workflow_id: str) -> Optional[PSOP]:
        result = self._load_psop_by_id(workflow_id)
        if result:
            logger.debug(f"[Retrieval] Loaded PSOP by id: {workflow_id}")
        else:
            logger.debug(f"[Retrieval] PSOP not found by id: {workflow_id}")
        return result

    def get_preflow_by_id(self, workflow_id: str) -> Optional[PreFlow]:
        return self.storage.load_preflow(workflow_id)

    def search_by_name(self, name_pattern: str, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        logger.debug(f"[Retrieval] search_by_name: pattern='{name_pattern}', type={workflow_type}")
        results = []
        name_lower = name_pattern.lower()
        if workflow_type in ("all", "psop"):
            for summary in self._list_psop_summaries():
                if name_lower in summary.name.lower():
                    results.append(summary)
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
                        created_at=preflow.created_at,
                    ))
        return results

    def search_by_tags(self, tags: List[str], match_all: bool = False, workflow_type: str = "all") -> List[
        WorkflowSearchResult]:
        results = []
        search_tags_lower = [t.lower() for t in tags]

        def matches_tags(wf_tags: Optional[List[str]]) -> bool:
            if not wf_tags:
                return False
            wf_lower = [t.lower() for t in wf_tags]
            if match_all:
                return all(st in wf_lower for st in search_tags_lower)
            else:
                return any(st in wf_lower for st in search_tags_lower)

        if workflow_type in ("all", "psop"):
            for summary in self._list_psop_summaries():
                if matches_tags(summary.tags):
                    results.append(summary)
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
                        created_at=preflow.created_at,
                    ))
        return results

    def search_by_description(self, keyword: str, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        results = []
        keyword_lower = keyword.lower()
        if workflow_type in ("all", "psop"):
            for summary in self._list_psop_summaries():
                if summary.description and keyword_lower in summary.description.lower():
                    results.append(summary)
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
                        created_at=preflow.created_at,
                    ))
        return results

    def get_psop_by_preflow(self, preflow_id: str) -> List[PSOP]:
        logger.debug(f"[Retrieval] get_psop_by_preflow: preflow_id={preflow_id}")
        results = []
        for summary in self._list_psop_summaries():
            if summary.related_preflow == preflow_id:
                psop = self._load_psop_by_id(summary.workflow_id)
                if psop:
                    results.append(psop)
        return results

    def list_recent_workflows(self, limit: int = 10, workflow_type: str = "all") -> List[WorkflowSearchResult]:
        results = []
        if workflow_type in ("all", "psop"):
            results.extend(self._list_psop_summaries())
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
                        created_at=preflow.created_at,
                    ))

        def _sort_key(x):
            if x.created_at.tzinfo:
                return x.created_at.timestamp()
            return x.created_at.replace(tzinfo=timezone.utc).timestamp()

        results.sort(key=_sort_key, reverse=True)
        return results[:limit]

    def _parse_json_response(self, llm_response: str) -> str:
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

    def _retrieve_names_by_intent(self, user_intent: str, top_n: int = 1) -> List[str]:
        summaries = self._list_psop_summaries()
        if not summaries:
            return []

        psop_list = [{
            "name": s.name,
            "description": s.description or "",
            "tags": s.tags or [],
            "user_intent": s.user_intent or "",
            "tasks": s.tasks_summary or "",
            "id": s.workflow_id
        } for s in summaries]

        psop_list_str = json.dumps(psop_list, ensure_ascii=False, indent=2)
        llm = get_llm_instance()
        prompt = get_retrieve_psop_prompt(user_intent, psop_list_str, top_n)

        try:
            _, llm_res = llm.ask_llm(prompt)
            selected_names = self._parse_json_response(llm_res)

            if not isinstance(selected_names, list):
                raise ValueError(f"Expected a JSON array of names, got: {type(selected_names)}")

            return selected_names[:top_n]
        except Exception as e:
            raise Exception(f"Failed to retrieve PSOP by intent: {e}") from e

    def retrieve_psop_by_intent(self, user_intent: str) -> Optional[PSOP]:
        logger.info(f"[Retrieval] retrieve_psop_by_intent: intent='{user_intent[:100]}...'")
        try:
            names = self._retrieve_names_by_intent(user_intent, top_n=1)
            if not names:
                return None

            summaries = self._list_psop_summaries()
            name_to_id = {s.name: s.workflow_id for s in summaries}
            psop_id = name_to_id.get(names[0])
            if psop_id:
                return self._load_psop_by_id(psop_id)
            return None
        except Exception as e:
            raise Exception(f"Failed to retrieve PSOP by intent: {e}") from e

    def retrieve_psop_by_intent_topn(
        self, user_intent: str, top_n: int = 5
    ) -> List[WorkflowSearchResult]:
        logger.info(f"[Retrieval] retrieve_psop_by_intent_topn: intent='{user_intent[:100]}...', top_n={top_n}")
        try:
            names = self._retrieve_names_by_intent(user_intent, top_n)
            name_to_summary = {s.name: s for s in self._list_psop_summaries()}
            results = [name_to_summary[name] for name in names if name in name_to_summary]
            logger.info(f"[Retrieval] TopN returned {len(results)} result(s) for intent")
            return results[:top_n]
        except Exception as e:
            raise Exception(f"Failed to retrieve PSOP topN by intent: {e}")
