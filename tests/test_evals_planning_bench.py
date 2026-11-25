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

"""Tests for the evals intent-to-PSOP planning benchmark.

Covers:
- dataset integrity: schema, dimension coverage, pool/skill references, gold files
- gold consistency: every reference PSOP must pass its own case requirements
- discrimination: single-aspect mutations of gold workflows must be rejected
- runner: gold mode exit code and pregen mode report generation
"""

import json

import pytest

from orchestrate.core.model.psop import PSOP

from evals.scoring.case_model import (
    DIMENSIONS,
    EVALS_DATA_DIR,
    load_cases,
    load_pool,
    validate_case_against_pool,
)
from evals.scoring.planner_scorer import PlannerScorer
from evals.scoring.selftest import (
    mutate_add_cycle,
    mutate_add_forbidden_skill,
    mutate_drop_aggregation,
    mutate_drop_branch,
    mutate_drop_required_skill,
    mutate_inject_pool_skill,
    mutate_swap_agent,
    run_selftest,
)


@pytest.fixture(scope="module")
def cases():
    return load_cases()


@pytest.fixture(scope="module")
def pools(cases):
    return {name: load_pool(name) for name in {case.agent_pool for case in cases}}


def _load_gold_psop(case) -> PSOP:
    path = EVALS_DATA_DIR / case.gold_psop_file
    with open(path, "r", encoding="utf-8") as handle:
        return PSOP.model_validate(json.load(handle))


def _case_by_id(cases, case_id):
    return next(case for case in cases if case.id == case_id)


# ===========================================================================
# dataset integrity
# ===========================================================================


class TestDatasetIntegrity:
    def test_case_count(self, cases):
        assert 35 <= len(cases) <= 60, f"unexpected case count: {len(cases)}"

    def test_all_dimensions_covered(self, cases):
        assert {case.dimension for case in cases} == set(DIMENSIONS)

    def test_unique_case_ids(self, cases):
        ids = [case.id for case in cases]
        assert len(ids) == len(set(ids))

    def test_pool_and_skill_references(self, cases, pools):
        errors = []
        for case in cases:
            errors.extend(validate_case_against_pool(case, pools[case.agent_pool]))
        assert not errors, errors

    def test_gold_files_exist_and_parse(self, cases):
        gold_ids = []
        for case in cases:
            if not case.gold_psop_file:
                continue
            path = EVALS_DATA_DIR / case.gold_psop_file
            assert path.exists(), f"missing gold file for {case.id}"
            assert isinstance(_load_gold_psop(case), PSOP)
            gold_ids.append(case.id)
        # every dimension must have reference answers for regression protection
        dims_with_gold = {
            case.dimension for case in cases if case.gold_psop_file
        }
        assert dims_with_gold == set(DIMENSIONS)
        assert len(gold_ids) >= 14

    def test_intents_nonempty(self, cases):
        for case in cases:
            assert case.intent.strip(), f"{case.id}: empty intent"


# ===========================================================================
# gold consistency: the evaluator must accept every reference workflow
# ===========================================================================


class TestGoldConsistency:
    def test_all_gold_psops_pass(self, cases, pools):
        failures = []
        for case in cases:
            if not case.gold_psop_file:
                continue
            report = PlannerScorer(case, pools[case.agent_pool]).score(
                _load_gold_psop(case)
            )
            if not report.passed:
                failures.append(f"{case.id}: {report.failures}")
        assert not failures, failures

    def test_skill_alias_matching_accepts_display_names(self, cases, pools):
        """PSOPs may reference a skill by its display name (the intent prompt
        exposes AgentSkill.name); the scorer must canonicalize both forms."""
        case = _case_by_id(cases, "TC-SGL-002")
        gold = _load_gold_psop(case)
        gold.steps[0].subtasks[0].skill = "SPN专线业务投诉诊断"
        report = PlannerScorer(case, pools["telecom"]).score(gold)
        assert report.passed, report.failures


# ===========================================================================
# mutation discrimination: corrupted workflows must be rejected
# ===========================================================================


class TestMutationDiscrimination:
    def test_drop_required_skill_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-PAR-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_drop_required_skill(_load_gold_psop(case))
        )
        assert not report.passed
        assert report.metrics["skill_recall"] < 1.0

    def test_swap_agent_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-PAR-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_swap_agent(_load_gold_psop(case), "SPN Domain Agent City2")
        )
        assert not report.passed
        assert report.metrics["agent_consistency"] == 0.0

    def test_add_cycle_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-PAR-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_add_cycle(_load_gold_psop(case))
        )
        assert not report.passed
        assert report.metrics["topology_valid"] == 0.0

    def test_drop_branch_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-BRH-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_drop_branch(_load_gold_psop(case))
        )
        assert not report.passed
        assert report.metrics["structure_pass"] == 0.0

    def test_drop_aggregation_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-AGG-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_drop_aggregation(_load_gold_psop(case))
        )
        assert not report.passed
        assert report.metrics["structure_pass"] == 0.0

    def test_add_forbidden_skill_fails(self, cases, pools):
        case = _case_by_id(cases, "TC-AMB-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_add_forbidden_skill(_load_gold_psop(case), "RAN Agent", "net-exec")
        )
        assert not report.passed
        assert report.metrics["skill_precision"] < 1.0

    def test_inject_pool_skill_breaks_refusal(self, cases, pools):
        case = _case_by_id(cases, "TC-OOS-001")
        report = PlannerScorer(case, pools["telecom"]).score(
            mutate_inject_pool_skill(_load_gold_psop(case), "RAN Agent", "analysis-eval")
        )
        assert not report.passed
        assert report.metrics["refusal_ok"] == 0.0

    def test_parse_failure_fails_in_scope_case(self, cases, pools):
        case = _case_by_id(cases, "TC-PAR-001")
        report = PlannerScorer(case, pools["telecom"]).score(None, "mock parse error")
        assert not report.passed
        assert report.metrics["schema_valid"] == 0.0

    def test_builtin_selftest_clean(self, cases, pools):
        assert run_selftest({case.id: case for case in cases}, pools) == []


# ===========================================================================
# runner behaviour
# ===========================================================================


class TestRunner:
    def test_gold_mode_exits_zero(self):
        from evals.run_eval import main

        assert main(["--mode", "gold"]) == 0

    def test_pregen_rejects_mutated_workflow(self, cases, tmp_path):
        from evals.run_eval import main

        case = _case_by_id(cases, "TC-PAR-001")
        mutated = mutate_add_cycle(_load_gold_psop(case))
        (tmp_path / "TC-PAR-001.json").write_text(
            mutated.model_dump_json(indent=2), encoding="utf-8"
        )
        exit_code = main(
            [
                "--mode", "pregen",
                "--psop-dir", str(tmp_path),
                "--output", str(tmp_path / "out"),
            ]
        )
        assert exit_code == 1
        report_md = tmp_path / "out" / "report.md"
        assert report_md.exists()

    def test_pregen_accepts_gold_workflow(self, cases, tmp_path):
        from evals.run_eval import main

        case = _case_by_id(cases, "TC-AGG-002")
        (tmp_path / "TC-AGG-002.json").write_text(
            _load_gold_psop(case).model_dump_json(indent=2), encoding="utf-8"
        )
        exit_code = main(
            [
                "--mode", "pregen",
                "--psop-dir", str(tmp_path),
                "--output", str(tmp_path / "out"),
            ]
        )
        assert exit_code == 0


# ===========================================================================
# online-mode prerequisites
# ===========================================================================


class TestOnlineCardBuilding:
    def test_pool_cards_parse_into_agentcards(self, pools):
        """The online runner must be able to build a2a AgentCard objects from
        the evaluation pools (same Parse path as the agent-card loader)."""
        from evals.run_eval import _pool_agent_cards

        for pool in pools.values():
            cards = _pool_agent_cards(pool, {agent.name for agent in pool.agents})
            assert len(cards) == len(pool.agents)
            assert all(card.name and card.skills for card in cards)
