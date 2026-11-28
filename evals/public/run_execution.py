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

"""Execution-capability evaluation: run planned PSOPs through the sandbox.

The planning benchmarks score what the planner *writes*; this harness scores
what the orchestration stack *does* with it. Every saved planning PSOP is
executed through the real workflow engine against the sandbox stub runtime
(``orchestrate.sandbox.run_sandbox``), exercising dispatch, parallel fan-out,
aggregation context, conditional routing and failure propagation.

Metrics per workflow:
- ``dispatch_completeness`` — completed stub interactions / planned subtasks;
- ``step_coverage``         — steps started / steps planned;
- ``aggregation_order``     — aggregation steps (layer > 0 or context_from or
  upstream via incoming edges) appear after every upstream step;
- ``skill_coverage``        — distinct skills dispatched / distinct planned;
- ``verdict``               — sandbox verdict + static check failures.

Fault resilience: a fraction of runs re-executes with ``scenario=error``; a
well-orchestrated run must fail gracefully (FAIL verdict, no runner crash).

Usage:
    python -m evals.public.run_execution --runs technique-oneshot-glm bench-taskbench-online --selfbuilt
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List

from orchestrate.core.model.psop import PSOP, StepType
from orchestrate.sandbox import StubScenario, run_sandbox
from orchestrate.sandbox.control_point import SandboxControlPoint

from evals.public.run_worfbench import BENCH_DEFAULT_CACHE, _load_parsed_items
from evals.run_eval import _pool_agent_cards
from evals.scoring.case_model import AgentPool, load_cases, load_pool
from evals.public.worfbench_data import build_agent_pool_dict

EVALS_OUTPUT = Path(__file__).resolve().parent.parent / "output"
SELF_BUILT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _pool_cards(pool: AgentPool):
    return _pool_agent_cards(pool, {agent.name for agent in pool.agents})


async def _execute_one(psop: PSOP, pool: AgentPool, intent: str, scenario: StubScenario) -> dict:
    cards = _pool_cards(pool)
    control_point = SandboxControlPoint()
    started = time.time()
    try:
        report = await run_sandbox(
            psop,
            cards,
            control_point,
            scenario=scenario,
            runtime_intent=intent,
            lang="en",
        )
    except Exception as exc:  # noqa: BLE001 - a crashed runner is itself a finding
        return {
            "crashed": True,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_s": round(time.time() - started, 2),
        }

    completed = sum(
        1 for interaction in report.stub_interactions
        if interaction.task_state == "TASK_STATE_COMPLETED"
    )
    # SelfLoop steps execute locally (no stub dispatch); exclude from the
    # dispatch denominator and count them separately.
    planned_subtasks = sum(
        len(step.subtasks) for step in psop.steps if step.type != StepType.SELF_LOOP
    )
    selfloop_steps = sum(1 for step in psop.steps if step.type == StepType.SELF_LOOP)
    position = {step: index for index, step in enumerate(report.execution_path)}

    aggregation_checks = []
    for step in psop.steps:
        upstream = set(step.context_from or [])
        for other in psop.steps:
            if other.name != step.name and any(
                step.name in (jump.step or "") for jump in (other.next or [])
            ):
                upstream.add(other.name)
        if not upstream:
            continue
        if step.name not in position:
            aggregation_checks.append(False)
            continue
        ordered = all(
            upstream_name in position and position[upstream_name] < position[step.name]
            for upstream_name in upstream
        )
        aggregation_checks.append(ordered)

    planned_skills = {
        subtask.skill for step in psop.steps
        if step.type != StepType.SELF_LOOP for subtask in step.subtasks
    }
    executed_skills = {interaction.skill for interaction in report.stub_interactions}

    return {
        "crashed": False,
        "verdict": str(report.verdict),
        "error": report.error,
        "dispatch_completeness": completed / planned_subtasks if planned_subtasks else 1.0,
        "step_coverage": len(set(report.execution_path)) / len(psop.steps) if psop.steps else 1.0,
        "aggregation_order": (
            sum(1 for ok in aggregation_checks if ok) / len(aggregation_checks)
            if aggregation_checks else 1.0
        ),
        "aggregation_steps": len(aggregation_checks),
        "selfloop_steps": selfloop_steps,
        "skill_coverage": (
            len(executed_skills & planned_skills) / len(planned_skills) if planned_skills else 1.0
        ),
        "interactions": len(report.stub_interactions),
        "failed_interactions": sum(
            1 for interaction in report.stub_interactions
            if interaction.task_state != "TASK_STATE_COMPLETED"
        ),
        "static_failures": [
            check.check_id for check in report.static_checks if str(check.status) == "fail"
        ],
        "static_checks": [
            {
                "id": check.check_id,
                "status": str(check.status),
                "detail": check.detail,
            }
            for check in report.static_checks
            if str(check.status) != "pass"
        ],
        "latency_s": round(time.time() - started, 2),
    }


async def _run_all(targets: List[dict], fault_ratio: float) -> List[dict]:
    results: List[dict] = []
    fault_slot = max(1, int(1 / fault_ratio)) if fault_ratio else 0
    for index, target in enumerate(targets):
        psop = _load_psop(Path(target["psop_path"]))
        entry = {key: target[key] for key in ("bench", "task", "item_id", "psop_path")}
        if psop is None:
            entry.update({"crashed": True, "error": "psop file unreadable", "scenario": "n/a"})
            results.append(entry)
            print(f"  [{target['bench']}/{target['item_id']}] unreadable psop", flush=True)
            continue
        scenario = (
            StubScenario.ERROR if fault_slot and index % fault_slot == 0 else StubScenario.SUCCESS
        )
        outcome = await _execute_one(psop, target["_pool"], target["_intent"], scenario)
        outcome.update(entry)
        outcome["scenario"] = str(scenario)
        results.append(outcome)
        verdict = outcome.get("verdict", "?")
        flag = "OK " if verdict == "pass" else "!! "
        print(
            f"  [{target['bench']}/{target['item_id']}] {flag}"
            f"dispatch={outcome.get('dispatch_completeness', 0):.2f} "
            f"steps={outcome.get('step_coverage', 0):.2f} "
            f"agg={outcome.get('aggregation_order', 0):.2f} "
            f"scenario={scenario.value} ({outcome.get('latency_s', 0)}s)",
            flush=True,
        )
    return results


def _load_psop(path: Path) -> Optional[PSOP]:
    try:
        return PSOP.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return None


def _infer_bench(run_dir: Path, record: dict) -> str:
    if record.get("bench"):
        return record["bench"]
    name = run_dir.name
    for bench in ("taskbench", "nestful", "workflowbench", "worfbench"):
        if f"-{bench}" in name or name.endswith(bench):
            return bench
    return "worfbench"


def collect_run_targets(run_dirs: List[Path]) -> List[dict]:
    """Pair psops/<item>.json with items.jsonl metadata; resolve pools eagerly.

    Shard dirs (base-a/-b/-c) are expanded automatically.
    """
    targets: List[dict] = []
    item_cache: Dict[str, dict] = {}
    for run_dir in run_dirs:
        candidates = [run_dir] + sorted(EVALS_OUTPUT.glob(f"{run_dir.name}-*"))
        seen_dirs = []
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "items.jsonl").exists():
                seen_dirs.append(candidate)
        if not seen_dirs:
            print(f"warning: skipping {run_dir} (no shard dir with items.jsonl)")
            continue
        psop_dirs = [
            (candidate, candidate / "psops") for candidate in seen_dirs
            if (candidate / "psops").is_dir()
        ]
        if not psop_dirs:
            print(f"warning: skipping {run_dir} (no psops/ dir)")
            continue
        for candidate, psop_dir in psop_dirs:
            items_path = candidate / "items.jsonl"
            for line in items_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                psop_path = psop_dir / f"{record['id']}.json"
                if not psop_path.exists():
                    continue
                bench = _infer_bench(candidate, record)
                task, item_id = record["task"], record["id"]
                cache_key = f"{bench}/{task}"
                try:
                    if cache_key not in item_cache:
                        parsed = _load_parsed_items(bench, BENCH_DEFAULT_CACHE[bench], task)
                        item_cache[cache_key] = {
                            item.id: (build_agent_pool_dict(item), item.instruction)
                            for item in parsed
                        }
                    pool_dict, intent = item_cache[cache_key].get(item_id), None
                    if pool_dict is None:
                        raise KeyError(item_id)
                    pool_dict, intent = item_cache[cache_key][item_id]
                    pool = AgentPool.model_validate(pool_dict)
                except Exception as exc:  # noqa: BLE001
                    print(f"warning: pool lookup failed for {item_id}: {exc}")
                    continue
                targets.append({
                    "bench": bench,
                    "task": task,
                    "item_id": item_id,
                    "psop_path": str(psop_path),
                    "_pool": pool,
                    "_intent": intent,
                })
    return targets


def collect_selfbuilt_targets() -> List[dict]:
    """Gold PSOPs of the self-built eval set executed against their pools."""
    cases = load_cases()
    pools = {name: load_pool(name) for name in {case.agent_pool for case in cases}}
    targets: List[dict] = []
    for case in cases:
        if not case.gold_psop_file:
            continue
        gold_path = SELF_BUILT_DATA_DIR / case.gold_psop_file
        if not gold_path.exists():
            continue
        targets.append({
            "bench": "selfbuilt",
            "task": case.dimension,
            "item_id": case.id,
            "psop_path": str(gold_path),
            "_pool": pools[case.agent_pool],
            "_intent": case.intent,
        })
    return targets


def aggregate(results: List[dict], with_per_bench: bool = True) -> dict:
    executed = [
        r for r in results
        if not r.get("crashed") and r.get("scenario") != str(StubScenario.ERROR)
    ]
    success = [r for r in executed if r.get("verdict") == "pass"]
    warned = [r for r in executed if r.get("verdict") == "warning"]
    fault_runs = [r for r in results if r.get("scenario") == str(StubScenario.ERROR)]

    def mean(key: str, subset: List[dict]) -> float:
        values = [r[key] for r in subset if key in r]
        return sum(values) / len(values) if values else 0.0

    graceful = sum(
        1 for r in fault_runs
        if not r.get("crashed") and r.get("verdict") == "fail"
    )
    summary = {
        "total": len(results),
        "executed": len(executed),
        "crashed": sum(1 for r in results if r.get("crashed")),
        "verdict_pass": len(success),
        "verdict_warning": len(warned),
        "verdict_fail_fault_runs": len(fault_runs) - graceful - sum(
            1 for r in fault_runs if r.get("crashed")
        ),
        "pass_rate": len(success) / len(executed) if executed else 0.0,
        "dispatch_completeness": mean("dispatch_completeness", executed),
        "step_coverage": mean("step_coverage", executed),
        "aggregation_order": mean("aggregation_order", executed),
        "skill_coverage": mean("skill_coverage", executed),
        "avg_latency_s": mean("latency_s", executed),
        "fault_runs": len(fault_runs),
        "fault_graceful_failures": graceful,
    }
    if with_per_bench:
        summary["per_bench"] = {
            bench: aggregate([r for r in results if r["bench"] == bench], with_per_bench=False)
            for bench in sorted({r["bench"] for r in results})
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.public.run_execution",
        description="Execution-capability evaluation over saved planning PSOPs",
    )
    parser.add_argument(
        "--runs", nargs="*", default=None,
        help="run dirs (containing items.jsonl + psops/); relative to evals/output",
    )
    parser.add_argument("--selfbuilt", action="store_true",
                        help="include the self-built gold PSOPs")
    parser.add_argument("--fault-ratio", type=float, default=0.2,
                        help="fraction of runs re-executed with the error scenario")
    parser.add_argument("--output", type=str, default=str(EVALS_OUTPUT / "execution"))
    args = parser.parse_args()

    targets: List[dict] = []
    if args.runs:
        run_dirs = [Path(r) if Path(r).is_absolute() else EVALS_OUTPUT / r for r in args.runs]
        targets.extend(collect_run_targets(run_dirs))
    if args.selfbuilt or not targets:
        targets.extend(collect_selfbuilt_targets())

    print(f"execution targets: {len(targets)}", flush=True)
    results = asyncio.run(_run_all(targets, args.fault_ratio))
    summary = aggregate(results)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "execution_report.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report: {output_dir / 'execution_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
