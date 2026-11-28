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

"""Project a generated PSOP into the node/edge graph WorfEval scores.

Nodes are flattened subtask descriptions in execution order; edges come from
the step-level ``next`` jumps — a jump from step A to step B connects every
subtask of A to every subtask of B (fan-out/fan-in). Subtasks inside one step
are parallel by PSOP semantics and therefore carry no edge between them.
"""

from typing import List, Tuple

from orchestrate.core.model.psop import PSOP


def _project(psop: PSOP, value_of) -> tuple:
    """Shared step-graph projection: nodes = value_of(subtask), edges = jumps."""
    nodes: List[str] = []
    ranges = {}
    for step in psop.steps:
        start = len(nodes)
        nodes.extend(value_of(subtask) for subtask in step.subtasks)
        ranges[step.name] = (start, len(nodes))

    step_names = {step.name for step in psop.steps}
    edges: set = set()
    for step in psop.steps:
        for jump in step.next or []:
            target = (jump.step or "").strip()
            if target in step_names and target != step.name:
                src_start, src_end = ranges[step.name]
                dst_start, dst_end = ranges[target]
                for i in range(src_start, src_end):
                    for j in range(dst_start, dst_end):
                        edges.add((i, j))
    return nodes, sorted(edges)


def psop_to_pred_graph(psop: PSOP) -> Tuple[List[str], List[Tuple[int, int]]]:
    """Natural-language projection: nodes are subtask descriptions."""
    return _project(psop, lambda subtask: subtask.description or "")


def psop_to_skill_graph(psop: PSOP) -> Tuple[List[str], List[Tuple[int, int]]]:
    """Tool-name projection: nodes are the selected skill ids.

    Used by benchmarks whose official metric matches tool/API call sequences
    (NESTFUL, WorkflowBench) rather than natural-language subtask texts.
    """
    return _project(psop, lambda subtask: subtask.skill or "")
