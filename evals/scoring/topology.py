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

"""Step-graph topology checks for the planning evaluator.

The PSOP step graph treats each step's ``next`` jump conditions as directed
edges. Jump targets named ``end`` are terminal pseudo-targets used by the
prompt examples and the execution engine, so they are excluded from the graph
but count as an outgoing edge for orphan detection.
"""

from typing import Dict, List, Optional, Set

END_STEP = "end"


def step_names(steps) -> Set[str]:
    return {step.name for step in steps}


def build_edges(steps) -> tuple:
    """Return (edges, has_real_out) for the step graph.

    ``edges`` maps step name -> list of real step-name targets. Jump targets
    named ``end`` are excluded from edges but still allowed by the scorer.
    ``has_real_out`` marks steps that jump to at least one real step.
    """
    names = step_names(steps)
    edges: Dict[str, List[str]] = {name: [] for name in names}
    has_real_out: Set[str] = set()
    for step in steps:
        for jump in step.next or []:
            target = (jump.step or "").strip()
            if not target:
                continue
            if target in names:
                edges[step.name].append(target)
                has_real_out.add(step.name)
    return edges, has_real_out


def detect_cycle(edges: Dict[str, List[str]]) -> Optional[List[str]]:
    """DFS cycle detection; returns the cycle path or None."""
    visited: Set[str] = set()
    stack: Set[str] = set()
    path: List[str] = []

    def dfs(node: str) -> Optional[List[str]]:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for neighbor in edges.get(node, []):
            if neighbor not in visited:
                cycle = dfs(neighbor)
                if cycle:
                    return cycle
            elif neighbor in stack:
                idx = path.index(neighbor)
                return path[idx:] + [neighbor]
        path.pop()
        stack.discard(node)
        return None

    for node in edges:
        if node not in visited:
            cycle = dfs(node)
            if cycle:
                return cycle
    return None


def strict_ancestors(edges: Dict[str, List[str]]) -> Dict[str, Set[str]]:
    """Transitive closure of strict ancestors for every step.

    Walks the *reverse* edges so ``closure[descendant]`` holds every upstream
    step that can reach it (excluding the step itself).
    """
    reverse: Dict[str, List[str]] = {name: [] for name in edges}
    for source, targets in edges.items():
        for target in targets:
            reverse[target].append(source)

    closure: Dict[str, Set[str]] = {name: set() for name in edges}

    def collect(node: str, seen: Set[str]) -> None:
        for prev in reverse.get(node, []):
            if prev in seen:
                continue
            seen.add(prev)
            collect(prev, seen)

    for name in edges:
        collect(name, closure[name])
    return closure


def is_strict_ancestor(closure: Dict[str, Set[str]], ancestor: str, descendant: str) -> bool:
    return ancestor in closure.get(descendant, set())


def has_incomparable_pair(
    edges: Dict[str, List[str]], closure: Dict[str, Set[str]]
) -> bool:
    """True when two steps exist with no ancestor relation in either direction."""
    names = list(edges)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            if first not in closure[second] and second not in closure[first]:
                return True
    return False


def isolated_steps(edges: Dict[str, List[str]], has_real_out: Set[str]) -> Set[str]:
    """Dead steps: nobody jumps to them and they jump to no real step.

    A step that only points to the terminal pseudo-target ``end`` (or has no
    ``next`` at all) and receives no incoming jump is unreachable dead code.
    """
    has_in = {target for targets in edges.values() for target in targets}
    return {
        name
        for name in edges
        if name not in has_in and name not in has_real_out
    }


def duplicate_step_names(steps) -> List[str]:
    seen: Set[str] = set()
    duplicates: List[str] = []
    for step in steps:
        if step.name in seen and step.name not in duplicates:
            duplicates.append(step.name)
        seen.add(step.name)
    return duplicates
