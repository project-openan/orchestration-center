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

from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowSearchResult(BaseModel):
    workflow_id: str = Field(..., description="Workflow unique ID")
    workflow_type: str = Field(..., description="Workflow type: psop or preflow")
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    tags: List[str] = Field(default_factory=list, description="Tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    score: float = Field(default=1.0, description="Search relevance score")
    user_intent: Optional[str] = Field(None, description="User intent text")
    related_preflow: Optional[str] = Field(None, description="Related PreFlow ID")
    tasks_summary: Optional[str] = Field(None, description="Concise summary of steps/tasks in the workflow")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
