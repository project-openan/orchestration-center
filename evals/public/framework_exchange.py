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

"""Export items for external-framework plan generation and convert plans back.

Runs in the PROJECT venv. Per bench:
- export: writes items.jsonl (id, task, instruction, actions, granularity)
  with sampling identical to run_worfbench smoke runs (per_task/take/seed);
- convert: converts plan JSON files into PSOPs scored by run_worfbench pregen.

Plan JSON contract: {"id": ..., "nodes": [...], "edges": [[i, j], ...]}.
For "description" benches (worfbench, taskbench) nodes are subtask
descriptions; for "skill" benches (nestful, workflowbench) nodes must be the
EXACT tool/API names chosen (official metrics match tool-name sequences).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\OpenAN\orchestration-center")

from evals.public.run_worfbench import BENCH_DEFAULT_CACHE, _load_parsed_items  # noqa: E402

BENCH_GRANULARITY = {
    "worfbench": "description",
    "taskbench": "description",
    "nestful": "skill",
    "workflowbench": "skill",
}
BENCH_TASKS = {
    "worfbench": [
        "alfworld", "intercodesql", "lumos", "os", "seal_tools",
        "toolalpaca", "toolbench", "webshop", "wikihow",
    ],
    "taskbench": ["huggingface", "multimedia", "dailylifeapis"],
    "nestful": ["main"],
    "workflowbench": ["main"],
}


def export_items(output: Path, bench: str, per_task: int, take: int, seed: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    granularity = BENCH_GRANULARITY[bench]
    lines = []
    total = 0
    for task in BENCH_TASKS[bench]:
        items = _load_parsed_items(bench, BENCH_DEFAULT_CACHE[bench], task)
        usable = [item for item in items if item.instruction and item.gold_nodes]
        from evals.public.worfbench_data import sample_parsed_items

        sampled = sample_parsed_items(usable, per_task, seed)
        if take:
            sampled = sampled[:take]
        for item in sampled:
            lines.append(json.dumps({
                "id": item.id,
                "task": task,
                "instruction": item.instruction,
                "actions": item.actions,
                "granularity": granularity,
            }, ensure_ascii=False))
        total += len(sampled)
    (output / f"items-{bench}.jsonl").write_text("\n".join(lines), encoding="utf-8")
    print(f"exported {total} items ({bench}, {granularity} granularity) -> {output / f'items-{bench}.jsonl'}")


def convert_plans(plans_dir: Path, psop_dir: Path, granularity: str = "description") -> int:
    """Convert plan JSON files into PSOP files for run_worfbench pregen scoring."""
    from orchestrate.core.model.psop import PSOP, Step, Task

    psop_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for plan_path in sorted(plans_dir.glob("*.json")):
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  skip unreadable plan {plan_path.name}: {exc}")
            continue
        nodes = [str(node).strip() for node in plan.get("nodes", []) if str(node).strip()]
        if not nodes:
            print(f"  skip empty plan {plan_path.name}")
            continue
        edges = [(int(a), int(b)) for a, b in plan.get("edges", [])]
        item_id = plan.get("id", plan_path.stem)
        steps = []
        targets_by_src: dict = {}
        for a, b in edges:
            targets_by_src.setdefault(a, []).append(b)
        for index, node in enumerate(nodes):
            targets = sorted(set(targets_by_src.get(index, [])))
            next_targets = [
                {"step": f"step{t + 1}", "condition": ""} for t in targets
            ] or [{"step": "end", "condition": "workflow complete"}]
            steps.append(Step(
                name=f"step{index + 1}",
                type="AllSuccess",
                subtasks=[Task(
                    description=node,
                    agent="Plan Operator",
                    # skill benches score on the skill projection: the chosen
                    # tool name IS the node value
                    skill=node if granularity == "skill" else f"op-{index}",
                )],
                next=next_targets,
            ))
        psop = PSOP(
            id=f"fw-{item_id}",
            name=f"fw-{item_id}",
            steps=steps,
            user_intent=plan.get("instruction", ""),
        )
        (psop_dir / f"{item_id}.json").write_text(psop.model_dump_json(indent=2), encoding="utf-8")
        count += 1
    print(f"converted {count} plans ({granularity} granularity) -> {psop_dir}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--convert", action="store_true")
    parser.add_argument("--bench", type=str, default="worfbench",
                        choices=list(BENCH_GRANULARITY))
    parser.add_argument("--plans-dir", type=str, required=False)
    parser.add_argument("--framework", type=str, default="framework")
    parser.add_argument("--per-task", type=int, default=10)
    parser.add_argument("--take", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default=str(
        Path(__file__).resolve().parent.parent / "output" / "framework-compare"))
    args = parser.parse_args()
    output = Path(args.output)
    if args.export:
        export_items(output, args.bench, args.per_task, args.take, args.seed)
    if args.convert:
        plans_dir = Path(args.plans_dir) if args.plans_dir else output / args.framework / f"plans-{args.bench}"
        convert_plans(plans_dir, output / args.framework / f"psops-{args.bench}", BENCH_GRANULARITY[args.bench])
    return 0


if __name__ == "__main__":
    sys.exit(main())
