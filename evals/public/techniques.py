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

"""Alternative orchestration techniques compared on the WorfBench harness.

All techniques share the same input (instruction + synthetic operator pool)
and the same output contract (a PSOP projected into a node/edge graph), so
they are scored by the identical WorfEval port:

- ``oneshot``        — the production single-call intent -> PSOP planner;
- ``pipeline``       — the PreFlow->PSOP style three-stage flow (extract
  subtasks -> match skills -> assemble graph), mirroring
  ``orchestrate.core.psop_generator.PsopGenerator``;
- ``repair``         — oneshot plus one self-critique/repair pass
  (NATURAL PLAN-style self-correction ablation);
- ``static-chain``   — no-LLM baseline: list every available action as a
  linear chain (dumb sequential orchestration floor);
- ``static-parallel``— no-LLM baseline: all actions as one parallel step.
"""

import json
from typing import List, Optional, Tuple

from orchestrate.core.model.psop import PSOP
from orchestrate.core.prompts import (
    get_choose_skill_prompt,
    get_intent_to_psop_prompt,
    get_preprocess_input_prompt,
)

from evals.public.worfbench_data import WorfBenchItem
from evals.scoring.case_model import AgentPool

TECHNIQUES = ("oneshot", "pipeline", "repair", "static-chain", "static-parallel")
LLM_TECHNIQUES = ("oneshot", "pipeline", "repair")


class TechniqueError(Exception):
    """Raised when a technique fails to produce a PSOP for an item."""


def _agent_cards_json(pool: AgentPool) -> str:
    cards = [
        {
            "name": agent.name,
            "description": agent.description,
            "skills": [
                {"name": skill.id, "description": skill.description}
                for skill in agent.skills
            ],
        }
        for agent in pool.agents
    ]
    return json.dumps(cards, ensure_ascii=False, indent=2)


def _pool_for(item: WorfBenchItem) -> AgentPool:
    from evals.public.worfbench_data import build_agent_pool_dict

    return AgentPool.model_validate(build_agent_pool_dict(item))


# ---------------------------------------------------------------------------
# no-LLM static baselines
# ---------------------------------------------------------------------------


def static_chain(item: WorfBenchItem) -> PSOP:
    """Every available action as one node, chained in listed order."""
    from orchestrate.core.model.psop import Step, Task

    agent = f"{item.source} Operator"
    actions = list(item.actions)
    steps = []
    for index, action in enumerate(actions, start=1):
        next_targets = (
            [{"step": f"step{index + 1}", "condition": ""}]
            if index < len(actions)
            else [{"step": "end", "condition": "workflow complete"}]
        )
        steps.append(
            Step(
                name=f"step{index}",
                subtasks=[Task(description=f"{action}: {item.actions[action]}", agent=agent, skill=action)],
                next=next_targets,
            )
        )
    if not steps:
        raise TechniqueError("no actions available for static baseline")
    return PSOP(id=f"static-chain-{item.id}", name=f"static-chain-{item.id}", steps=steps)


def static_parallel(item: WorfBenchItem) -> PSOP:
    """Every available action as one parallel step (no dependency edges)."""
    from orchestrate.core.model.psop import Step, Task

    agent = f"{item.source} Operator"
    subtasks = [
        Task(description=f"{action}: {item.actions[action]}", agent=agent, skill=action)
        for action in item.actions
    ]
    if not subtasks:
        raise TechniqueError("no actions available for static baseline")
    return PSOP(
        id=f"static-parallel-{item.id}",
        name=f"static-parallel-{item.id}",
        steps=[Step(name="step1", subtasks=subtasks, next=[{"step": "end", "condition": ""}])],
    )


# ---------------------------------------------------------------------------
# LLM techniques
# ---------------------------------------------------------------------------


def _parse_psop(generator, text: str) -> PSOP:
    from common.util.json_utils import parse_llm_json_response

    parsed = parse_llm_json_response(text, PSOP)
    if not isinstance(parsed, PSOP):
        raise TechniqueError("technique output is not a PSOP")
    return parsed


def oneshot(generator, item: WorfBenchItem) -> PSOP:
    """Production single-call planner (same code path as run_worfbench online)."""
    from orchestrate.core.intent_psop_generator import IntentWorkflowGeneratorError

    pool = _pool_for(item)
    from evals.run_eval import _pool_agent_cards

    cards = _pool_agent_cards(pool, {agent.name for agent in pool.agents})
    try:
        return generator.generate_psop_from_intent(
            item.instruction, cards, workflow_name=f"{item.source}-{item.id}"
        )
    except IntentWorkflowGeneratorError as exc:
        raise TechniqueError(str(exc)) from exc


def pipeline(generator, item: WorfBenchItem) -> PSOP:
    """Three-stage PreFlow->PSOP flow on top of the same LLM client."""
    pool = _pool_for(item)
    cards_json = _agent_cards_json(pool)
    schema_json = json.dumps(PSOP.model_json_schema(), ensure_ascii=False, indent=2)

    # stage 1: extract subtasks
    _, tasks_text = generator._llm.ask_llm(get_preprocess_input_prompt(item.instruction))
    tasks = _parse_json_list(tasks_text)
    if not tasks:
        raise TechniqueError("pipeline stage 1 produced no subtasks")

    # stage 2: match each subtask to an available skill
    _, skills_text = generator._llm.ask_llm(
        get_choose_skill_prompt(json.dumps(tasks, ensure_ascii=False), cards_json)
    )
    skill_map = _parse_json_dict(skills_text)

    # stage 3: assemble the PSOP with pinned tasks/skills as context
    pinned = (
        "## Pre-decomposed tasks and matched skills (use them as the workflow nodes)\n"
        + json.dumps(
            [{"task": task, "skill": skill_map.get(task, "none")} for task in tasks],
            ensure_ascii=False,
            indent=2,
        )
    )
    prompt = f"{get_intent_to_psop_prompt(item.instruction, cards_json, schema_json)}\n\n{pinned}"
    _, psop_text = generator._llm.ask_llm(prompt)
    return _parse_psop(generator, psop_text)


def repair(generator, item: WorfBenchItem, oneshot_psop: Optional[PSOP] = None) -> PSOP:
    """Oneshot generation plus one self-critique/repair pass."""
    from orchestrate.core.model.psop import PSOP as PSOPModel

    psop = oneshot_psop or oneshot(generator, item)
    pool = _pool_for(item)
    critique_prompt = f"""You previously produced the following workflow JSON for the instruction below.

## Instruction
{item.instruction}

## Available skills
{_agent_cards_json(pool)}

## Your previous workflow JSON
```json
{psop.model_dump_json(exclude_none=True)}
```

Check it for: (1) missing subtasks required by the instruction, (2) subtasks
that no skill can execute, (3) wrong dependencies (steps that should be
parallel vs sequential), (4) missing conditional routing. Output the corrected
complete workflow JSON only, in the same schema.
"""
    _, repaired_text = generator._llm.ask_llm(critique_prompt)
    return _parse_psop(generator, repaired_text)


# ---------------------------------------------------------------------------
# JSON helpers for intermediate stages
# ---------------------------------------------------------------------------


def _extract_json_block(text: str) -> Optional[str]:
    import re

    fenced = re.search(r"```(?:json)?\s*(.+?)```", text or "", re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return (text or "").strip()


def _parse_json_list(text: str) -> List[str]:
    block = _extract_json_block(text)
    try:
        value = json.loads(block)
    except Exception:
        return []
    if isinstance(value, dict):
        value = value.get("tasks") or value.get("actions") or []
    if not isinstance(value, list):
        return []
    return [str(entry) for entry in value if str(entry).strip()]


def _parse_json_dict(text: str) -> dict:
    block = _extract_json_block(text)
    try:
        value = json.loads(block)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def run_technique(technique: str, generator, item: WorfBenchItem) -> Tuple[PSOP, float]:
    """Dispatch one technique for one item; returns (psop, extra_latency_hint)."""
    import time

    started = time.time()
    if technique == "oneshot":
        psop = oneshot(generator, item)
    elif technique == "pipeline":
        psop = pipeline(generator, item)
    elif technique == "repair":
        psop = repair(generator, item)
    elif technique == "static-chain":
        psop = static_chain(item)
    elif technique == "static-parallel":
        psop = static_parallel(item)
    else:
        raise ValueError(f"unknown technique: {technique}")
    return psop, time.time() - started
