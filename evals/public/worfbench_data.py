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

"""Adapter from WorfBench gold items to the OpenAN intent-to-PSOP interface.

WorfBench items (``gold_traj/<task>/graph_eval.json``) carry a conversation
whose user turn holds the problem statement plus the available action list,
and whose assistant turn holds the gold workflow as ``Node:``/``Edges:`` text.
The adapter extracts both and exposes:

- ``instruction``  — fed to the planner as the natural-language intent;
- ``actions``      — the candidate skills, mapped onto one synthetic operator
  AgentCard per item (the WorfBench protocol exposes this list to the model);
- ``gold_nodes`` / ``gold_edges`` — the gold workflow graph (START/END
  markers stripped) used by the WorfEval scorer.
"""

import ast
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from evals.public.worf_eval import END_MARK, START_MARK

TASKS = (
    "alfworld", "intercodesql", "lumos", "os", "seal_tools",
    "toolalpaca", "toolbench", "webshop", "wikihow",
)

_NODE_LINE = re.compile(r"^\s*(\d+)\s*[.:]\s*(.+)$")
_EDGE_PAIR = re.compile(r"\(([^,()]+?)\s*,\s*([^(),]+?)\)")


@dataclass
class WorfBenchItem:
    id: str
    source: str
    instruction: str = ""
    actions: Dict[str, str] = field(default_factory=dict)
    gold_nodes: List[str] = field(default_factory=list)
    gold_edges: List[Tuple[int, int]] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)


def load_task_items(cache_dir: Path, task: str) -> List[dict]:
    """Load raw gold items of one task from the local cache."""
    path = Path(cache_dir) / task / "graph_eval.json"
    if not path.exists():
        raise FileNotFoundError(
            f"WorfBench cache missing: {path} (download instructions: evals/README.md)"
        )
    with open(path, "r", encoding="utf-8") as handle:
        items = json.load(handle)
    if not isinstance(items, list):
        raise ValueError(f"unexpected gold file layout in {path}")
    return items


def parse_item(raw: dict) -> WorfBenchItem:
    """Extract instruction / action list / gold graph from one raw item."""
    item = WorfBenchItem(id=str(raw.get("id", "")), source=str(raw.get("source", "")))
    user_text = ""
    assistant_text = ""
    for turn in raw.get("conversations", []):
        role = turn.get("role")
        if role == "user":
            user_text = turn.get("content", "")
        elif role == "assistant":
            assistant_text = turn.get("content", "")

    item.instruction, item.actions = _parse_user_turn(user_text, item.parse_warnings)
    item.gold_nodes, item.gold_edges = _parse_gold_graph(assistant_text, item.parse_warnings)
    return item


# Instruction markers, first match wins (each task domain uses its own).
_INSTRUCTION_MARKERS = ("My problem is:", "Your task is to:", "Task:", "Instruction:")
# Candidate-action list markers (each task domain uses its own).
_ACTIONS_MARKERS = (
    "The action list you can take",
    "The api list you can use",
    "The tool list you can select from",
    "api_list:",
    "The database tables and corresponding fields you can operate are",
)


def _parse_user_turn(user_text: str, warnings: List[str]) -> Tuple[str, Dict[str, str]]:
    lower = user_text.lower()

    # instruction start: first known marker
    start = None
    for marker in _INSTRUCTION_MARKERS:
        pos = lower.find(marker.lower())
        if pos != -1:
            start = pos + len(marker)
            break

    # actions marker: earliest known marker in the raw text
    actions_pos = -1
    actions_marker_len = 0
    for marker in _ACTIONS_MARKERS:
        pos = user_text.find(marker)
        if pos != -1 and (actions_pos == -1 or pos < actions_pos):
            actions_pos, actions_marker_len = pos, len(marker)

    if start is None:
        warnings.append("no instruction marker found")
        start = 0
    end = actions_pos if actions_pos != -1 else len(user_text)
    instruction = user_text[start:end].strip(" :\n\t")
    # webshop-style segment leftovers
    instruction = re.sub(r"\[SEP\]", " ", instruction)
    instruction = re.sub(r"\s+", " ", instruction).strip()
    instruction = re.sub(r"\s*Search\s*$", "", instruction).strip()

    if actions_pos == -1:
        warnings.append("no actions marker found")
        return instruction, {}
    tail = user_text[actions_pos + actions_marker_len:].lstrip(":").strip()
    actions = _parse_actions_tail(tail, warnings)
    if not actions:
        warnings.append("action list parsed empty")
    return instruction, actions


def _skill_id(text: str, index: int) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").lower()).strip("-")[:60]
    return sanitized or f"action_{index}"


def _literal_prefix(text: str) -> Optional[object]:
    """ast.literal_eval the first complete top-level list/dict in ``text``."""
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
            continue
        if char in "'\"":
            in_string, quote = True, char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                try:
                    return ast.literal_eval(text[: index + 1])
                except Exception:
                    return None
    return None


def _actions_from_literal(value, warnings: List[str]) -> Dict[str, str]:
    actions: Dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (list, tuple)):
                actions[str(key).strip()] = ", ".join(str(entry) for entry in item)
            else:
                actions[str(key).strip()] = str(item).strip()
    elif isinstance(value, list):
        for index, entry in enumerate(value, start=1):
            if isinstance(entry, str):
                actions.setdefault(_skill_id(entry, index), entry.strip())
            elif isinstance(entry, dict):
                name = str(
                    entry.get("api_name") or entry.get("name") or f"action_{index}"
                ).strip()
                description = str(
                    entry.get("api_description") or entry.get("description") or ""
                ).strip()
                actions.setdefault(name, description)
    if not actions:
        warnings.append("literal actions container empty")
    return actions


def _parse_actions_tail(tail: str, warnings: List[str]) -> Dict[str, str]:
    candidate = tail.strip().rstrip(".") or ""

    # structured literals (lists of dicts, dicts, lists of strings)
    first = candidate[:1]
    if first in "[{":
        literal = _literal_prefix(candidate)
        if literal is not None:
            actions = _actions_from_literal(literal, warnings)
            if actions:
                return actions

    actions: Dict[str, str] = {}
    for line in candidate.splitlines():
        line = line.strip()
        if not line:
            continue
        numbered = re.match(r"^\d+\s*[.)]\s*(.+)$", line)
        if numbered:
            text = numbered.group(1).strip()
            actions.setdefault(_skill_id(text, len(actions) + 1), text)
            continue
        named = re.match(r"^([A-Za-z0-9_\- ]{1,40}?)\s*:\s*(.+)$", line)
        if named:
            actions.setdefault(named.group(1).strip(), named.group(2).strip())
            continue
        bracketed = re.match(r"^([A-Za-z_]\w*)\s*\[([^\]]*)\]\s*\.?$", line)
        if bracketed:
            actions.setdefault(bracketed.group(1).strip(), bracketed.group(2).strip())
            continue
    return actions


def _parse_gold_graph(assistant_text: str, warnings: List[str]) -> Tuple[List[str], List[Tuple[int, int]]]:
    edge_pos = min(
        (pos for pos in (assistant_text.find("Edge:"), assistant_text.find("Edges:")) if pos != -1),
        default=-1,
    )
    node_text = assistant_text[:edge_pos] if edge_pos != -1 else assistant_text
    edge_text = assistant_text[edge_pos:] if edge_pos != -1 else ""

    nodes_by_id: Dict[int, str] = {}
    for line in node_text.splitlines():
        match = _NODE_LINE.match(line)
        if not match:
            continue
        node_id = int(match.group(1))
        if node_id in nodes_by_id:
            warnings.append(f"duplicate node id {node_id}")
            continue
        nodes_by_id[node_id] = match.group(2).strip()

    # Node list follows ascending id order; edges are declared against ids,
    # so convert to list-index space here.
    id_to_index = {node_id: pos for pos, node_id in enumerate(sorted(nodes_by_id))}
    nodes = [nodes_by_id[node_id] for node_id in sorted(nodes_by_id)]

    edges: List[Tuple[int, int]] = []
    for raw_u, raw_v in _EDGE_PAIR.findall(edge_text):
        u = _resolve_endpoint(raw_u.strip(), id_to_index, warnings)
        v = _resolve_endpoint(raw_v.strip(), id_to_index, warnings)
        if u is not None and v is not None:
            edges.append((u, v))
    return nodes, edges


def _resolve_endpoint(token: str, id_to_index: Dict[int, int], warnings: List[str]):
    """Map a node id (or START/END marker) to a list index; markers -> None."""
    upper = token.upper()
    if upper == START_MARK or upper == END_MARK:
        return None
    try:
        node_id = int(token)
    except ValueError:
        warnings.append(f"edge endpoint unparsed: {token}")
        return None
    if node_id not in id_to_index:
        warnings.append(f"edge endpoint references unknown node id {node_id}")
        return None
    return id_to_index[node_id]


def to_graph(item: WorfBenchItem) -> Tuple[List[str], List[Tuple[int, int]]]:
    """Gold graph in real-node space (markers already stripped)."""
    return item.gold_nodes, item.gold_edges


def sample_items(
    raw_items: List[dict], per_task: int, seed: int
) -> List[dict]:
    """Deterministic sample of raw items, ordered by id for reproducibility."""
    if per_task >= len(raw_items):
        sampled = list(raw_items)
    else:
        sampled = random.Random(seed).sample(raw_items, per_task)
    return sorted(sampled, key=lambda raw: str(raw.get("id", "")))


def sample_parsed_items(
    items: List["WorfBenchItem"], per_task: int, seed: int
) -> List["WorfBenchItem"]:
    """Deterministic sample of already-parsed items, ordered by id."""
    if per_task >= len(items):
        sampled = list(items)
    else:
        sampled = random.Random(seed).sample(items, per_task)
    return sorted(sampled, key=lambda item: item.id)


def build_agent_pool_dict(item: WorfBenchItem) -> dict:
    """One synthetic operator AgentCard whose skills are the item's actions."""
    skills = [
        {"id": name, "name": name, "description": description}
        for name, description in item.actions.items()
    ]
    return {
        "pool": f"worfbench-{item.source}",
        "description": f"Synthetic operator pool for WorfBench {item.source} items",
        "agents": [
            {
                "name": f"{item.source} Operator",
                "description": f"Tool operator agent for WorfBench {item.source} tasks",
                "version": "1.0.0",
                "capabilities": {"streaming": False},
                "defaultInputModes": ["application/json", "text/plain"],
                "defaultOutputModes": ["application/json", "text/plain"],
                "supportedInterfaces": [
                    {
                        "protocolBinding": "HTTP+JSON",
                        "protocolVersion": "1.0",
                        "url": "https://127.0.0.1:26600/a2a/json",
                        "tenant": "",
                    }
                ],
                "skills": skills,
            }
        ],
    }
