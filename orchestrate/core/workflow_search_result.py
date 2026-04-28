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

from typing import Optional, List, Dict, Any
from datetime import datetime


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