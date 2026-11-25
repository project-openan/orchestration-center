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

"""Requirement-based scorer for intent-to-PSOP planning outputs.

A generated PSOP is scored against the annotated requirements of an
:class:`evals.scoring.case_model.EvalCase`:

- schema validity (Pydantic ``PSOP`` instance supplied by the caller)
- step-graph topology (acyclic, no duplicate/orphan steps)
- skill recall over required (agent, skill) pairs
- precision over forbidden skills
- agent-skill consistency against the case's visible agent pool
  (hallucinated agents/skills are rejected; a pool skill may be referenced by
  id or by its display name, mirroring the intent prompt which exposes
  ``AgentSkill.name``)
- structural requirements: parallel fan-out, conditional branching,
  aggregation layer (``layer > 0`` or ``context_from``)
- dependency ordering between skill pairs (strict ancestor checks)
- capability coverage of subtask descriptions (keyword OR-sets)

Out-of-scope cases instead score refusal correctness: a pass requires that the
planner neither used a pool skill nor fabricated an unknown skill.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from orchestrate.core.model.psop import PSOP

from evals.scoring.case_model import AgentPool, EvalCase, SkillRef
from evals.scoring.topology import (
    build_edges,
    detect_cycle,
    duplicate_step_names,
    has_incomparable_pair,
    isolated_steps,
    is_strict_ancestor,
    strict_ancestors,
)

# Values a planner may use in Task.skill to mark an action as not executable
# by any pool capability ("none" is the marker defined by the intent prompt).
REFUSAL_SKILL_VALUES = {"none", ""}


@dataclass
class CaseReport:
    case_id: str
    dimension: str
    passed: bool = False
    out_of_scope: bool = False
    parse_error: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "dimension": self.dimension,
            "passed": self.passed,
            "out_of_scope": self.out_of_scope,
            "parse_error": self.parse_error,
            "metrics": self.metrics,
            "failures": self.failures,
        }


class PlannerScorer:
    """Score one case's planning output against its annotated requirements."""

    def __init__(self, case: EvalCase, pool: AgentPool):
        self.case = case
        visible = {agent.name: agent for agent in pool.agents if agent.name in set(case.agents)}
        self._visible = visible
        self._agent_alias: Dict[str, str] = {
            name.strip().lower(): name for name in visible
        }
        # skill alias (id or display name, case-insensitive) -> canonical skill id
        self._skill_alias: Dict[str, str] = {}
        self._agent_skills: Dict[str, Set[str]] = {}
        for name, agent in visible.items():
            owned: Set[str] = set()
            for skill in agent.skills:
                self._skill_alias[skill.id.strip().lower()] = skill.id
                if skill.name:
                    self._skill_alias[skill.name.strip().lower()] = skill.id
                owned.add(skill.id)
            self._agent_skills[name.strip().lower()] = owned
        self._forbidden_ids: Set[str] = {
            self._skill_alias[a.strip().lower()]
            for a in case.requirements.forbidden_skills
            if a.strip().lower() in self._skill_alias
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    def _canonical_skill(self, raw_skill: Optional[str]) -> Tuple[str, Optional[str]]:
        """Classify a PSOP ``Task.skill`` value.

        Returns (kind, canonical_id) with kind one of:
        "refusal_marker" | "pool_skill" | "unknown".
        """
        normalized = self._norm(raw_skill)
        if normalized in REFUSAL_SKILL_VALUES:
            return "refusal_marker", None
        canonical = self._skill_alias.get(normalized)
        if canonical is None:
            return "unknown", None
        return "pool_skill", canonical

    def _subtask_records(self, psop: PSOP) -> List[dict]:
        """Flatten (subtask, canonical skill classification, owning step)."""
        records: List[dict] = []
        for step in psop.steps:
            for subtask in step.subtasks:
                kind, canonical = self._canonical_skill(subtask.skill)
                records.append(
                    {
                        "agent": self._norm(subtask.agent),
                        "agent_raw": subtask.agent,
                        "skill_kind": kind,
                        "skill_canonical": canonical,
                        "skill_raw": subtask.skill,
                        "description": subtask.description or "",
                        "step": step.name,
                    }
                )
        return records

    def _requirement_skill_id(self, alias: str) -> Optional[str]:
        return self._skill_alias.get(alias.strip().lower())

    # ------------------------------------------------------------------
    # scoring
    # ------------------------------------------------------------------

    def score(self, psop: Optional[PSOP], parse_error: Optional[str] = None) -> CaseReport:
        report = CaseReport(
            case_id=self.case.id,
            dimension=self.case.dimension,
            out_of_scope=self.case.out_of_scope,
            parse_error=parse_error,
        )
        if self.case.out_of_scope:
            return self._score_refusal(psop, report)
        if parse_error or not isinstance(psop, PSOP):
            report.parse_error = parse_error or "planner output is not a PSOP instance"
            report.metrics = {
                "schema_valid": 0.0,
                "topology_valid": 0.0,
                "skill_recall": 0.0,
                "skill_precision": 0.0,
                "agent_consistency": 0.0,
                "structure_pass": 0.0,
                "order_pass": 0.0,
                "capability_coverage": 0.0,
            }
            report.failures.append(report.parse_error)
            return report
        return self._score_in_scope(psop, report)

    # -- refusal (out-of-scope) ---------------------------------------

    def _score_refusal(self, psop: Optional[PSOP], report: CaseReport) -> CaseReport:
        pool_hits = 0
        fabricated = 0
        if isinstance(psop, PSOP):
            for record in self._subtask_records(psop):
                if record["skill_kind"] == "pool_skill":
                    pool_hits += 1
                elif record["skill_kind"] == "unknown":
                    fabricated += 1
        refusal_ok = 1.0 if (pool_hits == 0 and fabricated == 0) else 0.0
        report.metrics = {
            "refusal_ok": refusal_ok,
            "pool_skill_hits": float(pool_hits),
            "fabricated_skills": float(fabricated),
        }
        if pool_hits:
            report.failures.append(
                f"out-of-scope intent used {pool_hits} pool skill(s) instead of refusing"
            )
        if fabricated:
            report.failures.append(
                f"out-of-scope intent fabricated {fabricated} unknown skill(s) instead of refusing"
            )
        report.passed = refusal_ok == 1.0
        return report

    # -- in-scope planning --------------------------------------------

    def _score_in_scope(self, psop: PSOP, report: CaseReport) -> CaseReport:
        failures: List[str] = []
        requirements = self.case.requirements
        steps = psop.steps
        records = self._subtask_records(psop)

        schema_valid = 1.0

        # 1. topology --------------------------------------------------
        duplicate_names = duplicate_step_names(steps)
        edges, has_out_edge = build_edges(steps)
        cycle = detect_cycle(edges)
        orphans = isolated_steps(edges, has_out_edge) if len(steps) > 1 else set()
        topology_valid = 1.0 if not (duplicate_names or cycle or orphans) else 0.0
        if duplicate_names:
            failures.append(f"duplicate step names: {duplicate_names}")
        if cycle:
            failures.append(f"step graph cycle: {' -> '.join(cycle)}")
        if orphans:
            failures.append(f"orphan steps (no in/out edges): {sorted(orphans)}")

        # 2. skill recall ----------------------------------------------
        matched = 0
        for ref in requirements.required_skills:
            if self._required_pair_matched(ref, records):
                matched += 1
        total_required = len(requirements.required_skills)
        recall = matched / total_required if total_required else 1.0
        if recall < 1.0:
            missing = [
                f"{ref.agent}/{ref.skill}"
                for ref in requirements.required_skills
                if not self._required_pair_matched(ref, records)
            ]
            failures.append(f"missing required skills: {missing}")

        # 3. forbidden-skill precision ----------------------------------
        forbidden_hits = sum(
            1 for record in records if record["skill_canonical"] in self._forbidden_ids
        )
        precision = 1.0 if not records else max(0.0, 1.0 - forbidden_hits / len(records))
        if forbidden_hits:
            used = sorted(
                {
                    record["skill_canonical"]
                    for record in records
                    if record["skill_canonical"] in self._forbidden_ids
                }
            )
            failures.append(f"forbidden skills used: {used}")

        # 4. agent-skill consistency ------------------------------------
        consistency_failures = self._consistency_failures(records)
        consistency = 1.0 if not consistency_failures else 0.0
        failures.extend(consistency_failures)

        # 5. structure ---------------------------------------------------
        structure_ok, structure_failures = self._structure_pass(steps, records)
        structure = 1.0 if structure_ok else 0.0
        failures.extend(structure_failures)

        # 6. ordering ----------------------------------------------------
        order_ok, order_failures = self._order_pass(steps)
        order = 1.0 if order_ok else 0.0
        failures.extend(order_failures)

        # 7. capability coverage ------------------------------------------
        coverage, coverage_failures = self._capability_coverage(records)
        failures.extend(coverage_failures)

        report.metrics = {
            "schema_valid": schema_valid,
            "topology_valid": topology_valid,
            "skill_recall": recall,
            "skill_precision": precision,
            "agent_consistency": consistency,
            "structure_pass": structure,
            "order_pass": order,
            "capability_coverage": coverage,
        }
        report.failures = failures
        report.passed = (
            topology_valid == 1.0
            and recall == 1.0
            and precision == 1.0
            and consistency == 1.0
            and structure_ok
            and order_ok
            and coverage == 1.0
        )
        return report

    # -- metric internals ----------------------------------------------

    def _required_pair_matched(self, ref: SkillRef, records: List[dict]) -> bool:
        target = self._requirement_skill_id(ref.skill)
        if target is None:
            return False
        agent_norm = self._norm(ref.agent)
        return any(
            record["agent"] == agent_norm and record["skill_canonical"] == target
            for record in records
        )

    def _consistency_failures(self, records: List[dict]) -> List[str]:
        failures: List[str] = []
        for record in records:
            agent_norm = record["agent"]
            if agent_norm not in self._agent_alias:
                failures.append(
                    f"unknown agent '{record['agent_raw']}' in step '{record['step']}'"
                )
                continue
            kind = record["skill_kind"]
            if kind == "refusal_marker":
                continue
            if kind == "unknown":
                failures.append(
                    f"fabricated skill '{record['skill_raw']}' in step '{record['step']}'"
                )
                continue
            canonical = record["skill_canonical"]
            if canonical not in self._agent_skills[agent_norm]:
                agent_name = self._agent_alias[agent_norm]
                failures.append(
                    f"agent '{agent_name}' does not own skill '{canonical}' "
                    f"(step '{record['step']}')"
                )
        return failures

    def _structure_pass(self, steps, records: List[dict]) -> Tuple[bool, List[str]]:
        structure = self.case.requirements.structure
        failures: List[str] = []
        step_count = len(steps)
        if step_count < structure.min_steps:
            failures.append(f"steps {step_count} < min_steps {structure.min_steps}")
        if structure.max_steps is not None and step_count > structure.max_steps:
            failures.append(f"steps {step_count} > max_steps {structure.max_steps}")
        if len(records) < structure.min_subtasks:
            failures.append(f"subtasks {len(records)} < min_subtasks {structure.min_subtasks}")

        edges, _ = build_edges(steps)
        if structure.requires_parallel:
            broad_step = any(len(step.subtasks) >= 2 for step in steps)
            incomparable = has_incomparable_pair(edges, strict_ancestors(edges))
            if not (broad_step or incomparable):
                failures.append("no parallel structure (no multi-subtask step or independent steps)")

        if structure.requires_branch:
            branch_found = False
            for step in steps:
                jumps = [
                    (jump.step or "").strip()
                    for jump in (step.next or [])
                    if (jump.step or "").strip()
                ]
                conditions = [(jump.condition or "").strip() for jump in (step.next or [])]
                distinct_targets = len(set(jumps)) >= 2
                labeled = sum(1 for condition in conditions if condition) >= 2
                if distinct_targets and labeled:
                    branch_found = True
                    break
            if not branch_found:
                failures.append(
                    "no conditional branch (no step with >= 2 distinct labeled jump targets)"
                )

        if structure.requires_aggregation:
            aggregated = any(
                step.layer > 0 or (step.context_from or []) for step in steps
            )
            if not aggregated:
                failures.append(
                    "no aggregation step (no step with layer > 0 or context_from)"
                )
        return not failures, failures

    def _order_pass(self, steps) -> Tuple[bool, List[str]]:
        skill_steps: Dict[str, Set[str]] = {}
        for step in steps:
            for subtask in step.subtasks:
                kind, canonical = self._canonical_skill(subtask.skill)
                if kind == "pool_skill" and canonical:
                    skill_steps.setdefault(canonical, set()).add(step.name)
        closure = strict_ancestors(build_edges(steps)[0])
        failures: List[str] = []
        for pair in self.case.requirements.required_order:
            first_id = self._requirement_skill_id(pair[0])
            second_id = self._requirement_skill_id(pair[1])
            if first_id is None or second_id is None:
                failures.append(f"order pair {pair}: skill not resolvable in visible pool")
                continue
            first_steps = skill_steps.get(first_id, set())
            second_steps = skill_steps.get(second_id, set())
            ordered = any(
                is_strict_ancestor(closure, before, after)
                for before in first_steps
                for after in second_steps
            )
            if not ordered:
                failures.append(
                    f"order violated: '{pair[0]}' must precede '{pair[1]}' "
                    f"(steps {sorted(first_steps)} -> {sorted(second_steps)})"
                )
        return not failures, failures

    def _capability_coverage(self, records: List[dict]) -> Tuple[float, List[str]]:
        groups = self.case.requirements.capability_keywords
        if not groups:
            return 1.0, []
        descriptions = [record["description"].strip().lower() for record in records]
        failures: List[str] = []
        covered = 0
        for group in groups:
            alternatives = [keyword.strip().lower() for keyword in group if keyword.strip()]
            hit = any(
                alternative and alternative in description
                for alternative in alternatives
                for description in descriptions
            )
            if hit:
                covered += 1
            else:
                failures.append(f"capability keywords not covered: {group}")
        return covered / len(groups), failures


def score_case(
    case: EvalCase,
    pool: AgentPool,
    psop: Optional[PSOP],
    parse_error: Optional[str] = None,
) -> CaseReport:
    """Convenience wrapper: score a single case."""
    return PlannerScorer(case, pool).score(psop, parse_error)
