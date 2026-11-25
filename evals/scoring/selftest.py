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

"""Mutation self-test helpers proving the evaluator has discriminating power.

Each mutation takes a gold (reference) PSOP and corrupts exactly one planning
aspect. A correct evaluator must reject every mutated workflow; the pytest
suite and ``run_eval --selftest`` both assert this.
"""

from typing import List

from orchestrate.core.model.psop import JumpCondition, PSOP, Step, Task

from evals.scoring.planner_scorer import PlannerScorer


def _copy(psop: PSOP) -> PSOP:
    return psop.model_copy(deep=True)


def _first_step_with_skill(psop: PSOP, skill_alias: str) -> Step:
    for step in psop.steps:
        for subtask in step.subtasks:
            if skill_alias.lower() in (subtask.skill or "").lower():
                return step
    raise ValueError(f"no subtask with skill '{skill_alias}' found in PSOP")


def mutate_drop_required_skill(psop: PSOP) -> PSOP:
    """Remove the subtasks of the second step (kills skill recall)."""
    mutated = _copy(psop)
    if len(mutated.steps) < 2:
        raise ValueError("mutation needs >= 2 steps")
    mutated.steps[1].subtasks = []
    return mutated


def mutate_swap_agent(psop: PSOP, wrong_agent: str) -> PSOP:
    """Assign the first subtask to an agent that does not own the skill."""
    mutated = _copy(psop)
    mutated.steps[0].subtasks[0].agent = wrong_agent
    return mutated


def mutate_add_cycle(psop: PSOP) -> PSOP:
    """Point the last step back to the first step (creates a topology cycle)."""
    mutated = _copy(psop)
    first_name = mutated.steps[0].name
    last = mutated.steps[-1]
    last.next = list(last.next or []) + [JumpCondition(step=first_name, condition="mutation")]
    return mutated


def mutate_drop_branch(psop: PSOP) -> PSOP:
    """Remove one labeled jump from a branching step (kills requires_branch)."""
    mutated = _copy(psop)
    for step in mutated.steps:
        jumps = list(step.next or [])
        labeled = [jump for jump in jumps if (jump.condition or "").strip()]
        if len(labeled) >= 2:
            step.next = [jump for jump in jumps if jump is not labeled[0]]
            return mutated
    raise ValueError("no branching step found in PSOP")


def mutate_drop_aggregation(psop: PSOP) -> PSOP:
    """Reset every aggregation marker (layer/context_from) to plain execution."""
    mutated = _copy(psop)
    found = False
    for step in mutated.steps:
        if step.layer > 0 or (step.context_from or []):
            step.layer = 0
            step.context_from = None
            found = True
    if not found:
        raise ValueError("no aggregation step found in PSOP")
    return mutated


def mutate_add_forbidden_skill(psop: PSOP, agent: str, skill: str) -> PSOP:
    """Append a subtask that uses a case-forbidden skill (kills precision)."""
    mutated = _copy(psop)
    mutated.steps[0].subtasks.append(
        Task(description="变异注入：直接下发变更操作", agent=agent, skill=skill)
    )
    return mutated


def mutate_inject_pool_skill(psop: PSOP, agent: str, skill: str) -> PSOP:
    """Append a pool-skill subtask to an out-of-scope plan (kills refusal_ok)."""
    mutated = _copy(psop)
    if not mutated.steps:
        raise ValueError("mutation needs at least one step")
    mutated.steps[0].subtasks.append(
        Task(description="变异注入：越界使用池内能力", agent=agent, skill=skill)
    )
    return mutated


def run_selftest(cases_by_id, pools) -> List[str]:
    """Run all built-in mutations; returns a list of failures (empty == pass).

    ``cases_by_id`` maps case id -> EvalCase, ``pools`` maps pool name -> AgentPool.
    """
    problems: List[str] = []

    def check(case_id: str, mutate) -> None:
        case = cases_by_id[case_id]
        pool = pools[case.agent_pool]
        gold = _load_gold_psop(case, cases_by_id, pools)
        mutated = mutate(gold)
        report = PlannerScorer(case, pool).score(mutated)
        if report.passed:
            problems.append(
                f"selftest: mutation on {case_id} still passes "
                f"(metrics={report.metrics})"
            )

    check("TC-PAR-001", mutate_drop_required_skill)
    check("TC-PAR-001", lambda p: mutate_swap_agent(p, "SPN Domain Agent City2"))
    check("TC-PAR-001", mutate_add_cycle)
    check("TC-BRH-001", mutate_drop_branch)
    check("TC-AGG-001", mutate_drop_aggregation)
    check("TC-AMB-001", lambda p: mutate_add_forbidden_skill(p, "RAN Agent", "net-exec"))
    check("TC-OOS-001", lambda p: mutate_inject_pool_skill(p, "RAN Agent", "analysis-eval"))
    return problems


def _load_gold_psop(case, cases_by_id, pools):
    from orchestrate.core.model.psop import PSOP
    import json
    from evals.scoring.case_model import EVALS_DATA_DIR

    if not case.gold_psop_file:
        raise ValueError(f"case {case.id} has no gold_psop_file")
    path = EVALS_DATA_DIR / case.gold_psop_file
    with open(path, "r", encoding="utf-8") as handle:
        return PSOP.model_validate(json.load(handle))
