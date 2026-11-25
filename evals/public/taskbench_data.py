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

"""Adapter for TaskBench (microsoft/JARVIS, NeurIPS 2024).

data.json is JSONL; each sample carries ``instruction``, ``tool_steps`` (gold
step descriptions), ``tool_nodes`` (gold operation assignment with arguments)
and ``tool_links`` (edges referencing operation names). Candidate tools come
from ``tool_desc.json``. Everything is mapped into the WorfBenchItem shape so
the existing WorfEval scoring pipeline can be reused unchanged:

- gold_nodes  = ``tool_steps`` texts (the planner is expected to produce
  subtask descriptions; WorfEval matches them textually);
- gold_edges  = ``tool_links`` resolved to node indices via ``tool_nodes``;
- actions     = the domain's candidate tools (id -> description).
"""

import json
from pathlib import Path
from typing import Dict, List

from evals.public.worfbench_data import WorfBenchItem

DOMAINS = ("huggingface", "multimedia", "dailylifeapis")


def _load_jsonish(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def _parse_sample(raw: dict, tool_catalog: Dict[str, str]) -> WorfBenchItem:
    item = WorfBenchItem(id=str(raw.get("id", "")), source="taskbench")
    item.instruction = (raw.get("instruction") or "").strip()

    tool_nodes = json.loads(raw.get("tool_nodes") or "[]")
    tool_steps = json.loads(raw.get("tool_steps") or "[]")
    tool_links = json.loads(raw.get("tool_links") or "[]")

    item.gold_nodes = [str(step).strip() for step in tool_steps if str(step).strip()]
    # resolve operation-name edges to node indices (first occurrence per name;
    # DAGs legitimately reuse a node for fan-out/fan-in). tool_nodes entries are
    # normally dicts with "task"; some samples carry plain strings.
    def _node_task(node) -> str:
        if isinstance(node, dict):
            return str(node.get("task", "")).strip()
        return str(node).strip()

    first_by_name: Dict[str, int] = {}
    for index, node in enumerate(tool_nodes):
        first_by_name.setdefault(_node_task(node), index)
    for link in tool_links:
        if not isinstance(link, dict):
            item.parse_warnings.append(f"edge unparsed: {link}")
            continue
        source_idx = first_by_name.get(str(link.get("source", "")).strip())
        target_idx = first_by_name.get(str(link.get("target", "")).strip())
        if source_idx is None or target_idx is None:
            item.parse_warnings.append(f"edge unresolved: {link}")
        elif source_idx == target_idx:
            item.parse_warnings.append(f"self-loop edge skipped: {link}")
        else:
            item.gold_edges.append((source_idx, target_idx))

    # gold node count should match tool_nodes; warn on mismatch
    if len(item.gold_nodes) != len(tool_nodes):
        item.parse_warnings.append(
            f"node count mismatch: {len(item.gold_nodes)} steps vs {len(tool_nodes)} tool_nodes"
        )
    item.actions = dict(tool_catalog)
    return item


def load_domain(cache_dir: Path, domain: str) -> List[WorfBenchItem]:
    """Parse one TaskBench domain into eval items."""
    domain_dir = Path(cache_dir) / domain
    data_path = domain_dir / "data.json"
    tool_desc_path = domain_dir / "tool_desc.json"
    if not data_path.exists():
        raise FileNotFoundError(f"TaskBench cache missing: {data_path}")

    tool_desc = _load_jsonish(tool_desc_path)
    catalog: Dict[str, str] = {}
    nodes = tool_desc.get("nodes", []) if isinstance(tool_desc, dict) else []
    for node in nodes:
        catalog[str(node["id"]).strip()] = str(node.get("desc", "")).strip()

    return [_parse_sample(raw, catalog) for raw in _load_jsonish(data_path)]
