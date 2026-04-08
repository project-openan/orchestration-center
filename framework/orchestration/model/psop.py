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
    type: StepType = Field(StepType.ALL_SUCCESS,
                           description="Step success condition "
                                       "- can be AllSuccess (all subtasks succeed) or AndSuccess (any subtask succeeds)",
                           examples=[StepType.ALL_SUCCESS, StepType.ANY_SUCCESS])
    subtasks: List[Task] = Field(..., description="List of subtasks within the step"
                                                  "no dependencies between subtasks, can be executed in parallel")
    next: Optional[List[JumpCondition]] = Field(None,
                                                description="Jump conditions to next steps. List of jump \
                                                conditions (if empty, unconditional jump)")


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