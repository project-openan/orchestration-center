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

"""Evaluate OpenAN intent-to-PSOP planning on the public WorfBench benchmark.

Pipeline per item:
1. parse the WorfBench gold item (instruction, action list, gold graph);
2. expose the item's action list as one synthetic operator AgentCard pool;
3. run ``IntentPsopGenerator`` (online, real LLM) or a gold-mirroring mock;
4. project the generated PSOP into a node/edge graph;
5. score with the ported WorfEval protocol (``evals/public/worf_eval.py``).

Usage:
    python -m evals.public.run_worfbench --mode mock --per-task 10
    python -m evals.public.run_worfbench --mode online --per-task 10 --tasks os,wikihow
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from orchestrate.core.model.psop import PSOP

from evals.public.worf_eval import eval_graph, eval_nodes
from evals.public.worfbench_data import (
    TASKS,
    WorfBenchItem,
    build_agent_pool_dict,
    load_task_items,
    parse_item,
    sample_parsed_items,
)
from evals.public.psop_adapter import psop_to_pred_graph, psop_to_skill_graph

EVALS_PUBLIC_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = EVALS_PUBLIC_DIR.parent / "output" / "worfbench"

# Public benchmark registry: default cache dirs and task domains per bench.
BENCHES = ("worfbench", "taskbench", "nestful", "workflowbench")
BENCH_DEFAULT_CACHE = {
    "worfbench": Path(r"D:\OpenAN\public-eval-cache\WorfBench\gold_traj"),
    "taskbench": Path(r"D:\OpenAN\public-eval-cache\TaskBench"),
    "nestful": Path(r"D:\OpenAN\public-eval-cache\NESTFUL"),
    "workflowbench": Path(r"D:\OpenAN\public-eval-cache\WorkflowBench"),
}


def _load_parsed_items(bench: str, cache_dir: Path, task: str):
    """Load parsed eval items for one task domain of any supported bench."""
    if bench == "worfbench":
        return [parse_item(raw) for raw in load_task_items(cache_dir, task)]
    if bench == "taskbench":
        from evals.public.taskbench_data import load_domain

        return load_domain(cache_dir, task)
    if bench == "nestful":
        from evals.public.nestful_data import load_items

        return load_items(cache_dir)
    if bench == "workflowbench":
        from evals.public.workflowbench_data import load_items

        return load_items(cache_dir)
    raise ValueError(f"unknown bench: {bench}")


def _default_tasks(bench: str) -> List[str]:
    if bench == "worfbench":
        return list(TASKS)
    if bench == "taskbench":
        from evals.public.taskbench_data import DOMAINS

        return list(DOMAINS)
    return ["main"]


# ---------------------------------------------------------------------------
# generation backends
# ---------------------------------------------------------------------------


def load_psop_file(path: Path) -> tuple:
    """Load a PSOP JSON file; returns (psop_or_None, parse_error_or_None)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return PSOP.model_validate(payload), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _mock_psop(item: WorfBenchItem):
    """Gold-mirroring workflow: one step per gold node, edges mirror gold.

    Exercises the full scoring pipeline without an LLM; with identical node
    texts and mirrored gold edges WorfEval must return F1 == 1.0. Skills use
    the gold node text when it is a valid skill id (tool-name granular
    benches) so the skill projection also self-calibrates.
    """
    from orchestrate.core.model.psop import PSOP, Step, Task

    fallback_skill = next(iter(item.actions), "none")
    agent = f"{item.source} Operator"
    count = len(item.gold_nodes)
    targets_by_src: Dict[int, List[int]] = {}
    for source, target in item.gold_edges:
        targets_by_src.setdefault(source, []).append(target)

    steps = []
    for index, node in enumerate(item.gold_nodes):
        step_number = index + 1
        step_skill = node if node in item.actions else fallback_skill
        targets = sorted(set(targets_by_src.get(index, [])))
        next_targets = [
            {"step": f"step{target + 1}", "condition": ""} for target in targets
        ] or [{"step": "end", "condition": "workflow complete"}]
        steps.append(
            Step(
                name=f"step{step_number}",
                type="AllSuccess",
                subtasks=[Task(description=node, agent=agent, skill=step_skill)],
                next=next_targets,
            )
        )
    return PSOP(
        id=f"worfbench-{item.id}",
        name=f"mock-{item.id}",
        steps=steps,
        user_intent=item.instruction,
    )


def _build_generator(models_config: Path, env_loader=None):
    if env_loader:
        env_loader()
    else:
        from evals.public.gateway_env import load_gateway_key

        load_gateway_key()
    import os

    os.environ["LLM_CONFIG_FILE"] = str(models_config)
    from orchestrate.core.intent_psop_generator import (
        IntentPsopGenerator,
        IntentWorkflowGeneratorError,
    )

    return IntentPsopGenerator(), IntentWorkflowGeneratorError


def _generate_online(generator, error_cls, item: WorfBenchItem, technique: str = "oneshot"):
    from evals.public.techniques import TechniqueError, run_technique

    started = time.time()
    try:
        psop, _ = run_technique(technique, generator, item)
        return psop, None, time.time() - started
    except TechniqueError as exc:
        return None, f"generation failed: {exc}", time.time() - started
    except Exception as exc:  # noqa: BLE001 - report any backend failure
        return None, f"{type(exc).__name__}: {exc}", time.time() - started


# ---------------------------------------------------------------------------
# scoring + aggregation
# ---------------------------------------------------------------------------


def _with_endpoints(nodes: List[str], edges) -> tuple:
    """Wrap a real-node graph with START/END marker nodes (official space).

    The reference WorfEval implementation scores graphs that include START/END
    markers, which connect otherwise disjoint gold components. Sources get a
    START in-edge, sinks an END out-edge, mirroring the gold text format.
    """
    marked_nodes = [ "START" ] + list(nodes) + [ "END" ]
    n = len(nodes)
    has_in = {target for _, target in edges}
    has_out = {source for source, _ in edges}
    marked_edges = {(a + 1, b + 1) for a, b in edges}
    for i in range(n):
        if (i + 1) not in has_in:
            marked_edges.add((0, i + 1))
        if (i + 1) not in has_out:
            marked_edges.add((i + 1, n + 1))
    return marked_nodes, sorted(marked_edges)


def _score_item(item: WorfBenchItem, psop, threshold: float, node_mode: str = "description") -> dict:
    if node_mode == "skill":
        pred_nodes, pred_edges = psop_to_skill_graph(psop)
    else:
        pred_nodes, pred_edges = psop_to_pred_graph(psop)
    gt_nodes, gt_edges = item.gold_nodes, item.gold_edges
    if pred_nodes and gt_nodes:
        pred_nodes_m, pred_edges_m = _with_endpoints(pred_nodes, pred_edges)
        gt_nodes_m, gt_edges_m = _with_endpoints(gt_nodes, gt_edges)
    else:
        pred_nodes_m, pred_edges_m = pred_nodes, pred_edges
        gt_nodes_m, gt_edges_m = gt_nodes, gt_edges
    return {
        "n_pred_nodes": len(pred_nodes),
        "n_gt_nodes": len(gt_nodes),
        "n_pred_edges": len(pred_edges),
        "n_gt_edges": len(gt_edges),
        "node": eval_nodes(pred_nodes, gt_nodes, gt_edges, threshold=threshold),
        "graph_official": eval_graph(
            pred_nodes_m, pred_edges_m, gt_nodes_m, gt_edges_m,
            threshold=threshold, mode="official",
        ),
        "graph_mapped": eval_graph(
            pred_nodes_m, pred_edges_m, gt_nodes_m, gt_edges_m,
            threshold=threshold, mode="mapped",
        ),
    }


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate(records: List[dict]) -> dict:
    ok = [r for r in records if r.get("error") is None]
    summary = {"total": len(records), "scored": len(ok), "errors": len(records) - len(ok)}
    for prefix in ("node", "graph_official", "graph_mapped"):
        for metric in ("precision", "recall", "f1_score"):
            key = f"{prefix}.{metric}"
            summary[key] = _mean([r["metrics"][prefix][metric] for r in ok])
    summary["avg_latency_s"] = _mean([r.get("latency_s", 0.0) for r in records])
    return summary


def render_markdown(report: dict) -> str:
    lines = ["# WorfBench x OpenAN 意图→PSOP 规划评测", ""]
    sample_desc = f"每域 {report['per_task']} 条 (seed={report['seed']}"
    if report.get("take"):
        sample_desc += f", take={report['take']}"
    sample_desc += ")"
    lines.append(
        f"- 模式: {report['mode']}  技术: {report.get('technique', 'oneshot')}"
        f"  抽样: {sample_desc}"
    )
    lines.append(f"- 节点匹配: char-bigram 余弦 (阈值 {report['threshold']}, 官方为 mpnet 句向量 — 本结果为保守下界)")
    lines.append(f"- 模型: {report['model']}")
    lines.append("")
    lines.append(
        "| 任务域 | 条数 | 评分 | Node F1 | Graph F1 (official) | Graph F1 (mapped) | 平均耗时(s) |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for task, bucket in report["tasks"].items():
        lines.append(
            f"| {task} | {bucket['scored']}/{bucket['total']} | {bucket['errors']} errors "
            f"| {bucket['node.f1_score']:.3f} | {bucket['graph_official.f1_score']:.3f} "
            f"| {bucket['graph_mapped.f1_score']:.3f} | {bucket['avg_latency_s']:.1f} |"
        )
    overall = report["overall"]
    lines.append(
        f"| **合计** | {overall['scored']}/{overall['total']} | {overall['errors']} errors "
        f"| **{overall['node.f1_score']:.3f}** | **{overall['graph_official.f1_score']:.3f}** "
        f"| **{overall['graph_mapped.f1_score']:.3f}** | {overall['avg_latency_s']:.1f} |"
    )
    lines.append("")
    lines.append("Node = LIS 序列匹配(枚举 gold 拓扑序取最优); Graph = 最大权节点匹配 + 连通分量子图匹配。")
    return "\n".join(lines)


def run(args) -> int:
    bench = args.bench
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] if args.tasks else _default_tasks(bench)
    if bench == "worfbench":
        unknown = [t for t in tasks if t not in TASKS]
        if unknown:
            print(f"unknown tasks: {unknown}; choose from {list(TASKS)}")
            return 2

    from evals.public.techniques import LLM_TECHNIQUES, TECHNIQUES

    if args.technique not in TECHNIQUES:
        print(f"unknown technique: {args.technique}; choose from {list(TECHNIQUES)}")
        return 2

    generator = None
    error_cls = None
    if args.mode == "online" and args.technique in LLM_TECHNIQUES:
        env_loader = None
        if args.env_key_var:
            from evals.public.gateway_env import load_env_var_from_file

            env_loader = (
                lambda: load_env_var_from_file(args.env_key_file, args.env_key_var)
            )
        generator, error_cls = _build_generator(Path(args.models_config), env_loader)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    psop_dir = output_dir / "psops"
    psop_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items.jsonl"
    records: List[dict] = []
    per_task_buckets: Dict[str, List[dict]] = {}
    # benchmarks scored at tool/API-name granularity use the skill projection
    node_mode = "skill" if bench in ("nestful", "workflowbench") else "description"

    def _flush() -> None:
        """Persist everything generated so far (crash-safe, observable)."""
        with open(items_path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        report_now = {
            "bench": bench,
            "mode": args.mode,
            "technique": args.technique,
            "per_task": args.per_task,
            "take": args.take,
            "seed": args.seed,
            "threshold": args.threshold,
            "model": "mock(gold-mirror)" if args.mode == "mock" else args.model,
            "tasks": {task: _aggregate(bucket) for task, bucket in per_task_buckets.items()},
            "overall": _aggregate(records),
        }
        with open(output_dir / "report.json", "w", encoding="utf-8") as handle:
            json.dump(report_now, handle, ensure_ascii=False, indent=2)
        with open(output_dir / "report.md", "w", encoding="utf-8") as handle:
            handle.write(render_markdown(report_now) + "\n")

    for task in tasks:
        parsed_items = _load_parsed_items(bench, args.cache_dir, task)
        sampled = sample_parsed_items(parsed_items, args.per_task, args.seed)
        if args.take:
            sampled = sampled[: args.take]
        if args.shard_count > 1:
            sampled = [
                item for index, item in enumerate(sampled)
                if index % args.shard_count == args.shard_index
            ]
        print(f"[{task}] {len(sampled)}/{len(parsed_items)} items selected"
              + (f" (shard {args.shard_index + 1}/{args.shard_count})" if args.shard_count > 1 else ""),
              flush=True)

        pregen_psops: Dict[str, tuple] = {}
        if args.mode == "pregen":
            psop_in_dir = Path(args.psop_dir) if args.psop_dir else None
            if psop_in_dir is None or not psop_in_dir.is_dir():
                print("pregen mode requires --psop-dir")
                return 2
            known_ids = {item.id for item in parsed_items}
            for path in sorted(psop_in_dir.glob("*.json")):
                if path.stem not in known_ids:
                    print(f"  warning: {path.name} matches no known item id, skipped")
                    continue
                psop, parse_error = load_psop_file(path)
                pregen_psops[path.stem] = (psop, parse_error)
            sampled = [item for item in parsed_items if item.id in pregen_psops]

        for item in sampled:
            record = {"id": item.id, "task": task, "warnings": item.parse_warnings}
            if args.mode == "mock":
                psop, error, latency = _mock_psop(item), None, 0.0
            elif args.mode == "pregen":
                psop, parse_error = pregen_psops[item.id]
                error = parse_error
                latency = 0.0
            elif args.technique.startswith("static"):
                try:
                    from evals.public.techniques import run_technique

                    psop, _ = run_technique(args.technique, generator, item)
                    error = None
                except Exception as exc:  # noqa: BLE001
                    psop, error = None, f"{type(exc).__name__}: {exc}"
                latency = 0.0
            else:
                existing = psop_dir / f"{item.id}.json"
                if args.resume and existing.exists():
                    psop, perr = load_psop_file(existing)
                    if psop is not None:
                        error, latency = None, 0.0
                        print(f"  [{item.id}] resumed", flush=True)
                    else:
                        psop, error, latency = _generate_online(generator, error_cls, item, args.technique)
                        print(f"  [{item.id}] {'FAIL: ' + error if error else 'generated'} ({latency:.1f}s)", flush=True)
                else:
                    psop, error, latency = _generate_online(generator, error_cls, item, args.technique)
                    print(f"  [{item.id}] {'FAIL: ' + error if error else 'generated'} ({latency:.1f}s)", flush=True)
            record.update({"error": error, "latency_s": round(latency, 2)})
            if psop is not None:
                record["metrics"] = _score_item(item, psop, args.threshold, node_mode)
                with open(psop_dir / f"{item.id}.json", "w", encoding="utf-8") as handle:
                    handle.write(psop.model_dump_json(indent=2))
            records.append(record)
            per_task_buckets.setdefault(task, []).append(record)
            _flush()

    report = {
        "mode": args.mode,
        "per_task": args.per_task,
        "seed": args.seed,
        "threshold": args.threshold,
        "model": "mock(gold-mirror)" if args.mode == "mock" else args.model,
        "tasks": {task: _aggregate(bucket) for task, bucket in per_task_buckets.items()},
        "overall": _aggregate(records),
    }
    _flush()

    # console summary (ASCII-safe)
    print("\n=== WorfBench eval summary ===")
    header = f"{'task':<14}{'scored':>8}{'nodeF1':>9}{'graphF1':>9}{'mappedF1':>10}"
    print(header)
    for task, bucket in report["tasks"].items():
        print(
            f"{task:<14}{bucket['scored']:>4}/{bucket['total']:<3}"
            f"{bucket['node.f1_score']:>9.3f}{bucket['graph_official.f1_score']:>9.3f}"
            f"{bucket['graph_mapped.f1_score']:>10.3f}"
        )
    overall = report["overall"]
    print(
        f"{'TOTAL':<14}{overall['scored']:>4}/{overall['total']:<3}"
        f"{overall['node.f1_score']:>9.3f}{overall['graph_official.f1_score']:>9.3f}"
        f"{overall['graph_mapped.f1_score']:>10.3f}"
    )
    print(f"report: {output_dir / 'report.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.public.run_worfbench",
        description="OpenAN planning x WorfBench (public benchmark) runner",
    )
    parser.add_argument("--mode", choices=["mock", "online", "pregen"], default="mock")
    parser.add_argument("--psop-dir", type=str, default=None,
                        help="pregen: directory of <item_id>.json PSOPs to score")
    parser.add_argument(
        "--bench", choices=list(BENCHES), default="worfbench",
        help="public benchmark: worfbench | taskbench | nestful | workflowbench",
    )
    parser.add_argument(
        "--technique",
        type=str,
        default="oneshot",
        help="oneshot | pipeline | repair | static-chain | static-parallel",
    )
    parser.add_argument("--tasks", type=str, default=None, help="comma list; default all domains of the bench")
    parser.add_argument("--per-task", type=int, default=10)
    parser.add_argument("--take", type=int, default=0, help="keep only the first N of the sampled set (comparable subset)")
    parser.add_argument("--shard-index", type=int, default=0, help="full-coverage sharding: process items where index %% count == shard_index")
    parser.add_argument("--shard-count", type=int, default=1, help="number of shards (use with --shard-index, --per-task >= item count)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--cache-dir", type=str, default=None,
                        help="bench data cache dir; defaults per bench under D:\\OpenAN\\public-eval-cache")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--resume", action="store_true",
                        help="online: skip items whose PSOP file already exists (long-run resume)")
    parser.add_argument(
        "--models-config", type=str, default=str(EVALS_PUBLIC_DIR / "models_gateway.yaml")
    )
    parser.add_argument(
        "--model", type=str, default="glm-5.3-flash (blue-zone gateway)", help="label for the report"
    )
    parser.add_argument(
        "--env-key-file", type=str, default=None,
        help="env file to load a missing API key variable from (e.g. repo .env)",
    )
    parser.add_argument(
        "--env-key-var", type=str, default=None,
        help="variable name to load from --env-key-file (e.g. DEEPSEEK_API_KEY)",
    )
    return parser


def main(argv=None) -> int:
    import os

    if os.environ.get("EVAL_DISABLE_FILE_LOG"):
        # shard processes must not share the orchestrator log file
        # (loguru rotation lock killed long runs)
        from loguru import logger

        logger.remove()
    args = build_parser().parse_args(argv)
    if not args.cache_dir:
        args.cache_dir = str(BENCH_DEFAULT_CACHE[args.bench])
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

