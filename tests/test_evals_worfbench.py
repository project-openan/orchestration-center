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

"""Tests for the WorfBench public-benchmark adapter and WorfEval port."""

import json
from pathlib import Path

import pytest

from orchestrate.core.model.psop import JumpCondition, PSOP, Step, Task

from evals.public import run_worfbench
from evals.public.psop_adapter import psop_to_pred_graph
from evals.public.worf_eval import (
    all_topological_sorts,
    char_ngram_cosine,
    eval_graph,
    eval_nodes,
    eval_plan,
    match_nodes,
)
from evals.public.worfbench_data import (
    build_agent_pool_dict,
    parse_item,
    sample_items,
)

WORFBENCH_CACHE = Path(r"D:\OpenAN\public-eval-cache\WorfBench\gold_traj")

SAMPLE_ITEM = {
    "source": "os",
    "conversations": [
        {"role": "system", "content": "You are a helpful task planner..."},
        {
            "role": "user",
            "content": (
                "Now, I will start a new problem in a new OS. My problem is:\n\n"
                "Locate all the text files (.txt) that contain the string \"Linux\".\n"
                "The action list you can take: bash: execute some bash code, take bash action\n"
                "finish: have finished the task, take finish action\n"
                "answer: have got the answer to the question, take answer action"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Node:\n"
                "1: execute bash code to find all .txt files containing \"Linux\"\n"
                "2: execute bash code to count occurrences in each file\n"
                "3: take answer action\n"
                "Edge: (START,1) (1,2) (2,3) (3,END)"
            ),
        },
    ],
    "target": "graph",
    "id": "os_999",
    "category": "eval",
}


# ===========================================================================
# WorfEval port
# ===========================================================================


class TestCharNgramCosine:
    def test_identical_text_is_one(self):
        assert char_ngram_cosine("list all files", "list all files") == 1.0

    def test_unrelated_text_below_threshold(self):
        assert char_ngram_cosine("bash code", "answer the question") < 0.3

    def test_paraphrase_scores_between(self):
        same = char_ngram_cosine(
            "execute bash code to list files", "execute bash code to list all files"
        )
        assert 0.3 < same <= 1.0


class TestMatchNodes:
    def test_exact_pairs(self):
        mapping = match_nodes(["a", "b"], ["a", "b"])
        assert mapping == {0: 0, 1: 1}

    def test_unmatched_is_negative_one(self):
        mapping = match_nodes(["totally different"], ["a", "b"])
        assert mapping[0] == -1

    def test_cross_order_assignment(self):
        mapping = match_nodes(["beta task", "alpha task"], ["alpha task", "beta task"])
        assert mapping == {0: 1, 1: 0}


class TestTopologicalSorts:
    def test_fanout_enumerates_orders(self):
        orders = all_topological_sorts(["a", "b", "c"], [(0, 2), (1, 2)])
        assert len(orders) == 2

    def test_cap_at_twenty(self):
        nodes = [f"n{i}" for i in range(6)]
        edges = [(0, 3), (1, 3), (2, 4), (3, 5), (4, 5)]
        assert len(all_topological_sorts(nodes, edges)) <= 20

    def test_large_graph_shortcut(self):
        nodes = [f"n{i}" for i in range(10)]
        orders = all_topological_sorts(nodes, [(0, 1)])
        assert orders == [nodes]


class TestEvalPlan:
    def test_identical_sequence_is_perfect(self):
        nodes = ["step one", "step two", "step three"]
        result = eval_plan(nodes, nodes)
        assert result["f1_score"] == 1.0

    def test_wrong_order_lowers_f1(self):
        gt = ["step one", "step two", "step three"]
        pred = ["step three", "step two", "step one"]
        result = eval_plan(pred, gt)
        assert result["f1_score"] < 1.0

    def test_missing_node_lowers_recall(self):
        gt = ["step one", "step two", "step three"]
        pred = ["step one", "step three"]
        result = eval_plan(pred, gt)
        assert result["recall"] == pytest.approx(2 / 3)

    def test_empty_pred_is_zero(self):
        assert eval_plan([], ["a"])["f1_score"] == 0.0


class TestEvalNodes:
    def test_gold_order_is_best(self):
        gt_nodes = ["a", "b", "c"]
        gt_edges = [(0, 1), (1, 2)]
        assert eval_nodes(["a", "b", "c"], gt_nodes, gt_edges)["f1_score"] == 1.0

    def test_parallel_gold_allows_any_order(self):
        gt_nodes = ["a", "b"]
        gt_edges = []
        result = eval_nodes(["b", "a"], gt_nodes, gt_edges)
        assert result["f1_score"] == 1.0


class TestEvalGraph:
    def test_identical_graph_is_perfect_mapped(self):
        nodes = ["a", "b", "c"]
        edges = [(0, 1), (1, 2)]
        result = eval_graph(nodes, edges, nodes, edges, mode="mapped")
        assert result["f1_score"] == 1.0

    def test_missing_edge_lowers_graph_f1(self):
        nodes = ["a", "b", "c"]
        gt_edges = [(0, 1), (1, 2)]
        result = eval_graph(nodes, [(0, 1)], nodes, gt_edges, mode="mapped")
        assert result["f1_score"] < 1.0

    def test_node_mismatch_lowers_recall(self):
        gt_nodes = ["a", "b"]
        gt_edges = [(0, 1)]
        result = eval_graph(["a", "zzz"], [(0, 1)], gt_nodes, gt_edges, mode="mapped")
        assert result["recall"] < 1.0

    def test_official_mode_runs(self):
        result = eval_graph(["a", "b"], [(0, 1)], ["a", "b"], [(0, 1)], mode="official")
        assert 0.0 <= result["f1_score"] <= 1.0


# ===========================================================================
# item parsing / pool building / sampling
# ===========================================================================


class TestItemParsing:
    def test_parse_sample_item(self):
        item = parse_item(SAMPLE_ITEM)
        assert item.id == "os_999"
        assert item.instruction.startswith("Locate all the text files")
        assert set(item.actions) == {"bash", "finish", "answer"}
        assert item.actions["bash"].startswith("execute some bash code")
        assert len(item.gold_nodes) == 3
        assert item.gold_nodes[0].startswith("execute bash code to find")
        assert item.gold_edges == [(0, 1), (1, 2)]

    def test_parse_handles_edges_label(self):
        variant = json.loads(json.dumps(SAMPLE_ITEM))
        variant["conversations"][2]["content"] = variant["conversations"][2]["content"].replace(
            "Edge:", "Edges:"
        )
        item = parse_item(variant)
        assert item.gold_edges == [(0, 1), (1, 2)]

    def test_pool_dict_exposes_actions_as_skills(self):
        item = parse_item(SAMPLE_ITEM)
        pool = build_agent_pool_dict(item)
        agent = pool["agents"][0]
        assert agent["name"] == "os Operator"
        assert {skill["id"] for skill in agent["skills"]} == {"bash", "finish", "answer"}

    def test_sampling_is_deterministic(self):
        raw = [{"id": f"os_{i}"} for i in range(50)]
        first = [item["id"] for item in sample_items(raw, 10, seed=7)]
        second = [item["id"] for item in sample_items(raw, 10, seed=7)]
        assert first == second and len(first) == 10


# ===========================================================================
# PSOP projection
# ===========================================================================


class TestPsopProjection:
    def _psop(self, steps_spec):
        steps = [
            Step(name=name, subtasks=[Task(description=desc, agent="a", skill="s") for desc in descs])
            for name, descs in steps_spec
        ]
        return PSOP(name="wf", steps=steps)

    def test_step_edge_fans_out(self):
        psop = self._psop([
            ("step1", ["a1", "a2"]),
            ("step2", ["b1"]),
        ])
        psop.steps[0].next = [JumpCondition(step="step2", condition="")]
        nodes, edges = psop_to_pred_graph(psop)
        assert nodes == ["a1", "a2", "b1"]
        assert edges == [(0, 2), (1, 2)]

    def test_parallel_subtasks_have_no_edges(self):
        psop = self._psop([("step1", ["a1", "a2", "a3"])])
        nodes, edges = psop_to_pred_graph(psop)
        assert len(nodes) == 3 and edges == []

    def test_end_jumps_are_dropped(self):
        psop = self._psop([("step1", ["a1"])])
        psop.steps[0].next = [JumpCondition(step="end", condition="")]
        nodes, edges = psop_to_pred_graph(psop)
        assert nodes == ["a1"] and edges == []


# ===========================================================================
# end-to-end mock run (no LLM quota)
# ===========================================================================


class TestMockRun:
    def test_mock_run_reaches_perfect_f1(self, tmp_path):
        exit_code = run_worfbench.main(
            [
                "--mode", "mock",
                "--tasks", "os",
                "--per-task", "5",
                "--output", str(tmp_path),
                "--cache-dir", str(WORFBENCH_CACHE),
            ]
        )
        assert exit_code == 0
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        bucket = report["tasks"]["os"]
        assert bucket["scored"] == 5 and bucket["errors"] == 0
        # the mock mirrors the gold workflow, so every metric must be 1.0
        assert bucket["node.f1_score"] == pytest.approx(1.0)
        assert bucket["graph_mapped.f1_score"] == pytest.approx(1.0)
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "items.jsonl").exists()

    def test_mock_run_survives_degraded_prediction(self, tmp_path):
        """A mutated gold (half the nodes dropped) must score below 1.0."""
        from evals.public.worfbench_data import load_task_items, parse_item

        raw_items = load_task_items(WORFBENCH_CACHE, "os")
        item = parse_item(raw_items[0])
        psop = run_worfbench._mock_psop(item)
        psop.steps = psop.steps[: max(1, len(psop.steps) // 2)]
        for index, step in enumerate(psop.steps[:-1], start=1):
            step.next = [JumpCondition(step=f"step{index + 1}", condition="")]
        psop.steps[-1].next = [JumpCondition(step="end", condition="done")]
        metrics = run_worfbench._score_item(item, psop, 0.6)
        assert metrics["node"]["f1_score"] < 1.0


@pytest.mark.skipif(
    not (WORFBENCH_CACHE / "os" / "graph_eval.json").exists(),
    reason="WorfBench cache not downloaded",
)
class TestRealDataSmoke:
    def test_os_items_parse(self):
        from evals.public.worfbench_data import load_task_items

        raw_items = load_task_items(WORFBENCH_CACHE, "os")
        parsed = [parse_item(raw) for raw in raw_items]
        with_instruction = [item for item in parsed if item.instruction]
        with_actions = [item for item in parsed if item.actions]
        with_gold = [item for item in parsed if item.gold_nodes]
        assert len(with_instruction) >= 0.9 * len(parsed)
        assert len(with_actions) >= 0.9 * len(parsed)
        assert len(with_gold) >= 0.9 * len(parsed)

    def test_every_task_domain_parses(self):
        """The adapter must handle every task domain's protocol format
        (numbered actions, api dicts, tool-dict lists, candidate-step lists,
        db-schema dicts, name-desc lines, WebShop segments)."""
        from evals.public.worfbench_data import TASKS, load_task_items

        for task in TASKS:
            raw_items = load_task_items(WORFBENCH_CACHE, task)
            parsed = [parse_item(raw) for raw in raw_items[:20]]
            good = [
                item for item in parsed
                if item.instruction and item.actions and item.gold_nodes
            ]
            assert len(good) >= 0.9 * len(parsed), (
                f"{task}: only {len(good)}/{len(parsed)} full-parse"
            )

    def test_domain_formats_yield_expected_action_shapes(self):
        from evals.public.worfbench_data import load_task_items, parse_item

        checks = {
            "os": lambda a: "bash" in a,
            "alfworld": lambda a: "go-to-recep" in a,
            "wikihow": lambda a: len(a) >= 5,
            "webshop": lambda a: set(a) <= {"search", "click"},
            "toolalpaca": lambda a: any(not name.startswith("action_") for name in a),
            "intercodesql": lambda a: len(a) >= 2,
            "lumos": lambda a: any("VQA" in name for name in a),
            "seal_tools": lambda a: any("encryptData" in name for name in a),
            "toolbench": lambda a: any("link" in name.lower() for name in a),
        }
        for task, check in checks.items():
            raw_items = load_task_items(WORFBENCH_CACHE, task)
            item = parse_item(raw_items[0])
            assert check(item.actions), f"{task}: unexpected action shape {list(item.actions)[:3]}"


# ===========================================================================
# additional public benches: TaskBench / NESTFUL / WorkflowBench
# ===========================================================================


@pytest.mark.skipif(
    not (Path(r"D:\OpenAN\public-eval-cache\TaskBench\huggingface\data.json")).exists(),
    reason="TaskBench cache not downloaded",
)
class TestTaskBenchAdapter:
    def test_domains_parse(self):
        from evals.public.taskbench_data import DOMAINS, load_domain

        for domain in DOMAINS:
            items = load_domain(Path(r"D:\OpenAN\public-eval-cache\TaskBench"), domain)
            assert len(items) > 100, f"{domain}: only {len(items)} items"
            good = [i for i in items if i.instruction and i.gold_nodes and i.actions]
            assert len(good) >= 0.95 * len(items), f"{domain}: {len(good)}/{len(items)}"

    def test_dag_edges_resolved(self):
        from evals.public.taskbench_data import load_domain

        items = load_domain(Path(r"D:\OpenAN\public-eval-cache\TaskBench"), "huggingface")
        dags = [i for i in items if i.gold_edges]
        assert dags, "no DAG samples parsed"
        for item in dags[:20]:
            for a, b in item.gold_edges:
                assert a < len(item.gold_nodes) and b < len(item.gold_nodes)
                assert a != b

    def test_mock_calibration(self, tmp_path):
        from evals.public.run_worfbench import main

        exit_code = main([
            "--bench", "taskbench", "--mode", "mock", "--tasks", "multimedia",
            "--per-task", "5", "--output", str(tmp_path),
        ])
        assert exit_code == 0
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert report["tasks"]["multimedia"]["node.f1_score"] == pytest.approx(1.0)
        assert report["tasks"]["multimedia"]["graph_official.f1_score"] == pytest.approx(1.0)


@pytest.mark.skipif(
    not (Path(r"D:\OpenAN\public-eval-cache\NESTFUL\nestful_data.jsonl")).exists(),
    reason="NESTFUL cache not downloaded",
)
class TestNestfulAdapter:
    def test_items_parse(self):
        from evals.public.nestful_data import load_items

        items = load_items(Path(r"D:\OpenAN\public-eval-cache\NESTFUL"))
        assert len(items) > 1500
        good = [i for i in items if i.instruction and i.gold_nodes and i.actions]
        assert len(good) >= 0.95 * len(items)

    def test_data_dependency_edges(self):
        from evals.public.nestful_data import load_items

        items = load_items(Path(r"D:\OpenAN\public-eval-cache\NESTFUL"))
        with_edges = [i for i in items if i.gold_edges]
        assert len(with_edges) > 0.5 * len(items)
        for item in with_edges[:20]:
            for a, b in item.gold_edges:
                assert a < b  # dependencies point forward

    def test_mock_calibration(self, tmp_path):
        from evals.public.run_worfbench import main

        exit_code = main([
            "--bench", "nestful", "--mode", "mock", "--per-task", "5",
            "--output", str(tmp_path),
        ])
        assert exit_code == 0
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert report["overall"]["node.f1_score"] == pytest.approx(1.0)
        assert report["overall"]["graph_official.f1_score"] == pytest.approx(1.0)


@pytest.mark.skipif(
    not (Path(r"D:\OpenAN\public-eval-cache\WorkflowBench\data_samples.json")).exists(),
    reason="WorkflowBench cache not downloaded",
)
class TestWorkflowBenchAdapter:
    def test_items_parse(self):
        from evals.public.workflowbench_data import load_items

        items = load_items(Path(r"D:\OpenAN\public-eval-cache\WorkflowBench"))
        assert len(items) >= 40
        good = [i for i in items if i.instruction and i.gold_nodes and i.actions]
        assert len(good) >= 0.8 * len(items)

    def test_mock_calibration(self, tmp_path):
        from evals.public.run_worfbench import main

        exit_code = main([
            "--bench", "workflowbench", "--mode", "mock", "--per-task", "5",
            "--output", str(tmp_path),
        ])
        assert exit_code == 0
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert report["overall"]["node.f1_score"] == pytest.approx(1.0)


class TestBenchRegistry:
    def test_runner_rejects_unknown_bench(self):
        from evals.public.run_worfbench import main

        with pytest.raises(SystemExit):
            main(["--bench", "no-such-bench", "--mode", "mock", "--per-task", "1"])


# ===========================================================================
# orchestration technique comparison
# ===========================================================================


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def ask_llm(self, prompt):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("FakeLLM ran out of canned replies")
        return None, self.replies.pop(0)


def _fake_generator(replies):
    from types import SimpleNamespace

    return SimpleNamespace(_llm=FakeLLM(replies))


class TestStaticTechniques:
    def _item(self):
        return parse_item(SAMPLE_ITEM)

    def test_static_chain_lists_actions_in_order(self):
        from evals.public.techniques import static_chain

        psop = static_chain(self._item())
        assert len(psop.steps) == 3
        assert psop.steps[0].subtasks[0].skill == "bash"
        assert psop.steps[1].subtasks[0].skill == "finish"
        assert psop.steps[2].subtasks[0].skill == "answer"
        assert psop.steps[0].next[0].step == "step2"

    def test_static_parallel_has_no_edges(self):
        from evals.public.techniques import static_parallel

        psop = static_parallel(self._item())
        assert len(psop.steps) == 1
        assert len(psop.steps[0].subtasks) == 3
        nodes, edges = psop_to_pred_graph(psop)
        assert len(nodes) == 3 and edges == []

    def test_unknown_technique_rejected(self):
        from evals.public.techniques import run_technique

        with pytest.raises(ValueError):
            run_technique("no-such-technique", None, self._item())


class TestLLMTechniques:
    def _item(self):
        return parse_item(SAMPLE_ITEM)

    def test_pipeline_makes_three_calls_and_assembles(self):
        from evals.public.techniques import pipeline

        psop_json = (
            '{"name": "wf", "steps": ['
            '{"name": "step1", "subtasks": [{"description": "step a", "agent": "os Operator", "skill": "bash"}], '
            '"next": [{"step": "step2", "condition": ""}]}, '
            '{"name": "step2", "subtasks": [{"description": "step b", "agent": "os Operator", "skill": "answer"}], '
            '"next": [{"step": "end", "condition": ""}]}]}'
        )
        gen = _fake_generator([
            '```json\n["step a", "step b"]\n```',
            '```json\n{"step a": "bash", "step b": "answer"}\n```',
            f"```json\n{psop_json}\n```",
        ])
        psop = pipeline(gen, self._item())
        assert len(gen._llm.prompts) == 3
        assert len(psop.steps) == 2
        assert psop.steps[0].subtasks[0].skill == "bash"

    def test_pipeline_empty_stage1_raises(self):
        from evals.public.techniques import TechniqueError, pipeline

        gen = _fake_generator(["no json here"])
        with pytest.raises(TechniqueError):
            pipeline(gen, self._item())

    def test_repair_uses_single_extra_call(self):
        from evals.public.techniques import repair

        item = self._item()
        original = run_worfbench._mock_psop(item)
        repaired_json = json.loads(original.model_dump_json())
        repaired_json["steps"] = repaired_json["steps"][:1]
        gen = _fake_generator([json.dumps(repaired_json)])
        psop = repair(gen, item, oneshot_psop=original)
        assert len(gen._llm.prompts) == 1
        assert len(psop.steps) == 1
