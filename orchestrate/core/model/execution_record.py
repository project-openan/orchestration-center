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

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"


class ExecutionRecord(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid4()),
                              description="Unique execution record identifier")
    psop_id: str = Field(..., description="ID of the executed PSOP workflow")
    psop_name: str = Field("", description="Name of the executed PSOP workflow")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Execution completion timestamp")
    status: ExecutionStatus = Field(ExecutionStatus.RUNNING, description="Execution status")
    execution_history: List[Dict[str, Any]] = Field(default_factory=list,
                                                      description="Step-level execution history")
    final_psop: Optional[Dict[str, Any]] = Field(None,
                                                   description="Final PSOP state with task statuses")
    events: List[Dict[str, Any]] = Field(default_factory=list,
                                           description="Agent interaction events for replay")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    catalog_version: Optional[str] = Field(None, description="Approved role catalog release the workflow was resolved against")
    config_version: Optional[str] = Field(None, description="Instance registry release used for role resolution")
    policy_version: Optional[str] = Field(None, description="Binding policy version applied during resolution")
    execution_scope: Optional[str] = Field(None, description="Execution scope as tenant/site/business_object")
    bindings: Optional[List[Dict[str, Any]]] = Field(None, description="Frozen role-to-instance bindings")
    card_fingerprints: Optional[List[str]] = Field(None, description="Fingerprints of the frozen AgentCard snapshots")
    resolution_snapshot: Optional[Dict[str, Any]] = Field(None, description="Immutable resolution envelope, independent of final task statuses and event retention")
    template_fingerprint: Optional[str] = None
    snapshot_fingerprint: Optional[str] = None
    confirm_fingerprint: Optional[str] = Field(None, description="Preview confirmation digest the execution was confirmed against; absent for legacy entries without a confirmation digest")
    overrides_applied: Optional[Dict[str, Any]] = Field(None, description="Manual re-selection traceability: task_overrides, group_overrides and tie_break applied to the resolution")
