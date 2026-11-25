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

"""Adapter for NESTFUL (IBM, Apache 2.0): nested sequences of API calls.

The official NESTFUL metric matches the **sequence of tool calls** (name +
arguments), so this adapter scores at tool-name granularity: gold nodes are
the call names in order and gold edges come from the ``$var_N.result$`` data
dependencies between calls. The runner projects the planner's PSOP into the
skill-name graph for this bench (see ``psop_adapter.psop_to_skill_graph``).
"""

import json
from pathlib import Path
from typing import List

from evals.public.worfbench_data import WorfBenchItem


def load_items(cache_dir: Path) -> List[WorfBenchItem]:
    path = Path(cache_dir) / "nestful_data.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"NESTFUL cache missing: {path}")
    items: List[WorfBenchItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        item = WorfBenchItem(id=str(raw.get("sample_id", "")), source="nestful")
        item.instruction = (raw.get("input") or "").strip()

        calls = raw.get("output") or []
        item.gold_nodes = [str(call.get("name", "")).strip() for call in calls]

        # data dependencies: arguments referencing "$var_N.result$"
        label_to_index = {
            str(call.get("label", "")).strip(): index for index, call in enumerate(calls)
        }
        edges = set()
        for index, call in enumerate(calls):
            arguments = call.get("arguments") or {}
            if not isinstance(arguments, dict):
                continue
            for value in arguments.values():
                if isinstance(value, str) and value.startswith("$var_"):
                    dep_index = label_to_index.get(value.split(".")[0].strip())
                    if dep_index is not None and dep_index < index:
                        edges.add((dep_index, index))
        item.gold_edges = sorted(edges)

        item.actions = {
            str(tool.get("name", "")).strip(): str(tool.get("description", "")).strip()
            for tool in (raw.get("tools") or [])
            if str(tool.get("name", "")).strip()
        }
        if not item.actions:
            item.parse_warnings.append("no candidate tools")
        items.append(item)
    return items
