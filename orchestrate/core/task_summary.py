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

"""Derive the one-line task summary shown in workflow search results.

This lives here, in the domain layer, rather than next to the database handlers:
both the file backend and the SQL backend need the same summary, so keeping it
in ``orchestrate.handlers.psop_processor`` forced the storage layer to import
the handler layer (a reverse dependency).
"""

from typing import Optional

from orchestrate.core.model.psop import PSOP

#: Steps and subtasks are capped so one huge PSOP cannot dominate the summary.
MAX_STEPS = 8
MAX_SUBTASKS = 3
MAX_TASKS = 12


def generation_binding(psop: PSOP) -> str:
    """Return the generation binding of a PSOP: "role" or "instance".

    Role-catalog generations carry ``binding="role"`` subtasks; everything
    else (including workflows stored before the binding split) projects as
    "instance". Shared by both persistence backends so search results can
    label same-named role/instance generations of one solution package.
    """
    if any(task.binding == "role" for step in psop.steps for task in step.subtasks):
        return "role"
    return "instance"


def build_tasks_summary(psop: PSOP) -> Optional[str]:
    """Return a compact ``[step] task`` summary of a PSOP, or ``None``."""
    task_descriptions = []
    for step in psop.steps[:MAX_STEPS]:
        for task in step.subtasks[:MAX_SUBTASKS]:
            desc = (task.description or "").strip()
            if desc:
                task_descriptions.append(f"[{step.name}] {desc}")
    if not task_descriptions:
        return None
    return "; ".join(task_descriptions[:MAX_TASKS])
