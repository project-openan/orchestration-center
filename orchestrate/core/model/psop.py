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

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


"""
PSOP (Parallel-Standard Operation Process): Runtime workflow for system execution.
Defines explicit tasks and their relationships at agent granularity.
Each task specifies which agent and skill to use.
"""

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class StepType(str, Enum):
    ALL_SUCCESS = "AllSuccess"
    ANY_SUCCESS = "AnySuccess"


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique task identifier")
    description: str = Field(..., description="Task description", examples=['Execute energy saving analysis'])
    agent: str = Field(..., description="Name of the agent executing the task")
    skill: str = Field(..., description="Skill required to execute the task",
                       examples=['best_effort_energy_saving', 'extreme_backup_energy_saving'])
    status: TaskStatus = Field(TaskStatus.PENDING, description="Task execution status")


class JumpCondition(BaseModel):
    step: str = Field(..., description="Target step name")
    condition: str = Field(..., description="Condition description for jumping")


class Step(BaseModel):
    name: str = Field(..., description="Step identifier", examples=['step1', 'step2'])
    type: StepType = Field(
        StepType.ALL_SUCCESS,
        description="Step success condition - "
        "AllSuccess (all subtasks succeed) or AndSuccess (any subtask succeeds)",
        examples=[StepType.ALL_SUCCESS, StepType.ANY_SUCCESS],
    )
    subtasks: List[Task] = Field(..., description="List of subtasks within the step"
                                                  "no dependencies between subtasks, can be executed in parallel")
    next: Optional[List[JumpCondition]] = Field(None,
                                                description="Jump conditions to next steps. List of jump \
                                                conditions (if empty, unconditional jump)")
    layer: int = Field(0, description="Orchestration layer level. 0 = execution layer (leaf agents), "
                                      "1+ = aggregation layers (can consume lower layer outputs)")
    context_from: Optional[List[str]] = Field(None,
                                              description="List of step names whose outputs should be provided as "
                                                          "context to this step's agents. "
                                                          "If set, the execution engine will inject prior step results "
                                                          "into each agent's input.")


class PSOP(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()),
                    description="Unique workflow identifier (auto-generated if not provided)")
    name: str = Field(..., description="Workflow name", examples=['energy_saving_process', 'fault_diagnosis_process'])
    description: Optional[str] = Field(None, description="Brief work description, empty by default")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    steps: List[Step] = Field(..., description="List of steps in the agent collaboration workflow")
    related_preflow: Optional[str] = Field(None,
                                           description="Associated Preflow ID that this PSOP was generated from,\
                                            empty by default")
    user_intent: Optional[str] = Field(None,
                                       description="Original user intent that generated this workflow,\
                                        empty by default")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for quick filtering")