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

"""Case and agent-pool models for the intent-to-PSOP planning evaluation set.

Each case (``evals/data/cases.jsonl``) declares a natural-language intent, the
agent pool visible to the planner, and requirement annotations a well-planned
PSOP must satisfy. Scoring is requirement-based (not exact-match), following
the evaluation philosophy of WorfBench (graph structure checks), TravelPlanner
(constraint pass rates), NATURAL PLAN (difficulty dimensions) and tau-bench
(rule following / refusal).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

EVALS_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Evaluation dimensions. Each maps to a capability dimension of the planner
# and to the public benchmark the dimension design derives from (see README).
DIMENSIONS: Dict[str, str] = {
    "single_step": "单步原子规划（NATURAL PLAN）",
    "parallel_fanout": "并行扇出（WorfBench / PlanBench）",
    "conditional_branch": "条件分支路由（WorfBench / TravelPlanner）",
    "aggregation_layer": "汇聚分层（WorfBench 子图）",
    "cross_domain_collab": "跨域协同（OpenAN 样例工作流）",
    "out_of_scope_refusal": "越界拒答（tau-bench 规则遵循）",
    "ambiguous_intent": "模糊意图保守规划（NATURAL PLAN / tau-bench）",
    "long_chain": "长链路多阶段（PlanBench / NATURAL PLAN）",
}

DIFFICULTIES = {"easy", "medium", "hard"}


class SkillRef(BaseModel):
    """A required (agent, skill) assignment pair."""

    agent: str = Field(..., description="Agent name that must execute the skill")
    skill: str = Field(..., description="Skill id or display name")


class StructureRequirements(BaseModel):
    min_steps: int = Field(1, ge=0, description="Minimum number of PSOP steps")
    max_steps: Optional[int] = Field(None, ge=1, description="Maximum number of PSOP steps")
    min_subtasks: int = Field(1, ge=0, description="Minimum total number of subtasks")
    requires_parallel: bool = Field(False, description="Parallel execution must be expressible")
    requires_branch: bool = Field(False, description="Conditional routing must be expressible")
    requires_aggregation: bool = Field(
        False, description="An aggregation step (layer > 0 or context_from) must exist"
    )


class CaseRequirements(BaseModel):
    required_skills: List[SkillRef] = Field(default_factory=list)
    forbidden_skills: List[str] = Field(
        default_factory=list, description="Skill ids that must not appear in the plan"
    )
    required_order: List[List[str]] = Field(
        default_factory=list,
        description="Pairs [skillA, skillB]: the step holding skillA must be a "
        "strict topological ancestor of a step holding skillB",
    )
    structure: StructureRequirements = Field(default_factory=StructureRequirements)
    capability_keywords: List[List[str]] = Field(
        default_factory=list,
        description="Each inner list is an OR-set of keywords; every OR-set must be "
        "covered by at least one subtask description",
    )


class EvalCase(BaseModel):
    id: str
    dimension: str
    difficulty: str = "medium"
    title: str
    intent: str
    agent_pool: str = "telecom"
    agents: List[str] = Field(..., description="Agent names visible to the planner")
    source_benchmark: str = Field(
        "openan_native",
        description="Public benchmark the case design derives from: planbench | "
        "natural_plan | travelplanner | tau_bench | worfbench | openan_native",
    )
    notes: str = ""
    requirements: CaseRequirements = Field(default_factory=CaseRequirements)
    out_of_scope: bool = Field(False, description="Intent is out of scope; planner should refuse")
    gold_psop_file: Optional[str] = Field(
        None, description="Reference PSOP path relative to evals/data, e.g. gold/TC-PAR-001.json"
    )

    @field_validator("dimension")
    @classmethod
    def _dimension_known(cls, value: str) -> str:
        if value not in DIMENSIONS:
            raise ValueError(f"unknown dimension '{value}', expected one of {sorted(DIMENSIONS)}")
        return value

    @field_validator("difficulty")
    @classmethod
    def _difficulty_known(cls, value: str) -> str:
        if value not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty '{value}', expected one of {sorted(DIFFICULTIES)}")
        return value


class PoolSkill(BaseModel):
    id: str
    name: str = Field("", description="Display name (may be used by the LLM instead of the id)")
    description: str = ""


class PoolAgent(BaseModel):
    name: str
    description: str = ""
    skills: List[PoolSkill] = Field(default_factory=list)


class AgentPool(BaseModel):
    pool: str
    description: str = ""
    agents: List[PoolAgent] = Field(default_factory=list)


def load_cases(path: Optional[Path] = None) -> List[EvalCase]:
    """Load the JSONL case set; blank lines and ``#`` comments are skipped."""
    path = Path(path) if path else EVALS_DATA_DIR / "cases.jsonl"
    cases: List[EvalCase] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(EvalCase.model_validate(json.loads(stripped)))
            except Exception as exc:
                raise ValueError(f"invalid eval case at {path}:{line_no}: {exc}") from exc
    if not cases:
        raise ValueError(f"no eval cases found in {path}")
    return cases


def load_pool(name_or_path) -> AgentPool:
    """Load an agent pool by file path or by pool name (agent_pool_<name>.json)."""
    path = Path(name_or_path)
    if not path.exists():
        path = EVALS_DATA_DIR / f"agent_pool_{name_or_path}.json"
    if not path.exists():
        raise FileNotFoundError(f"agent pool not found: {name_or_path}")
    with open(path, "r", encoding="utf-8") as handle:
        return AgentPool.model_validate(json.load(handle))


def _resolve_skill(agent: PoolAgent, skill_alias: str) -> Optional[str]:
    alias = skill_alias.strip().lower()
    for skill in agent.skills:
        if alias in {skill.id.strip().lower(), skill.name.strip().lower()}:
            return skill.id
    return None


def validate_case_against_pool(case: EvalCase, pool: AgentPool) -> List[str]:
    """Cross-check a case against its pool; returns a list of data errors."""
    errors: List[str] = []
    by_name = {agent.name: agent for agent in pool.agents}
    for name in case.agents:
        if name not in by_name:
            errors.append(f"{case.id}: agent '{name}' not in pool '{pool.pool}'")
    for ref in case.requirements.required_skills:
        agent = by_name.get(ref.agent)
        if agent is None:
            errors.append(f"{case.id}: required agent '{ref.agent}' not in pool")
        elif _resolve_skill(agent, ref.skill) is None:
            errors.append(f"{case.id}: agent '{ref.agent}' does not own skill '{ref.skill}'")
    all_skills = {
        skill.id.strip().lower()
        for agent in pool.agents
        for skill in agent.skills
    }
    for skill_alias in case.requirements.forbidden_skills:
        if skill_alias.strip().lower() not in all_skills:
            errors.append(f"{case.id}: forbidden skill '{skill_alias}' not in pool")
    for pair in case.requirements.required_order:
        if len(pair) != 2:
            errors.append(f"{case.id}: required_order pairs must have exactly 2 entries")
            continue
        for alias in pair:
            owner = next(
                (a for a in pool.agents if _resolve_skill(a, alias)), None
            )
            if owner is None:
                errors.append(f"{case.id}: order skill '{alias}' not in pool")
    return errors
