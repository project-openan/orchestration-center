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

"""Adapter for WorkflowBench (WorkflowLLM, OpenBMB).

Samples carry ``query``, the candidate ``apis`` list and ``annotated_code`` —
a Python-style linear workflow script where each step assigns the result of an
API call to a variable. Gold nodes are the API names in code order and gold
edges are the linear chain (Apple Shortcuts semantics are sequential). Scoring
happens at API-name granularity via the skill-name projection.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import List

from evals.public.worfbench_data import WorfBenchItem

_CALL_LINE = re.compile(r"=\s*([A-Za-z_][\w.]*)\s*\(")


def load_items(cache_dir: Path) -> List[WorfBenchItem]:
    path = Path(cache_dir) / "data_samples.json"
    if not path.exists():
        raise FileNotFoundError(f"WorkflowBench cache missing: {path}")
    samples = json.loads(path.read_text(encoding="utf-8"))
    items: List[WorfBenchItem] = []
    for entry in samples if isinstance(samples, list) else []:
        query = str(entry.get("query", "")).strip()
        item = WorfBenchItem(
            id=f"wf-{hashlib.md5(query.encode('utf-8')).hexdigest()[:8]}",
            source="workflowbench",
        )
        item.instruction = query
        apis = [str(api).strip() for api in (entry.get("apis") or []) if str(api).strip()]
        item.actions = {api: api for api in apis}

        code = str(entry.get("annotated_code") or "")
        # api ids are dotted ("is.workflow.actions.url"); code calls them with
        # underscores ("is_workflow_actions_url(...)"). Normalize for matching
        # but keep the canonical dotted id as the gold node text.
        code_to_id = {api.replace(".", "_"): api for api in apis}
        calls = []
        for match in _CALL_LINE.finditer(code):
            code_name = match.group(1).strip()
            canonical = code_to_id.get(code_name)
            if canonical and (not calls or calls[-1] != canonical):
                calls.append(canonical)
        item.gold_nodes = calls
        item.gold_edges = [(i, i + 1) for i in range(len(calls) - 1)]
        if not item.gold_nodes:
            item.parse_warnings.append("no api calls parsed from annotated_code")
        items.append(item)
    return items
