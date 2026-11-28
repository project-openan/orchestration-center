# -*- coding: utf-8 -*-
"""Build the technique-comparison table from multiple run_worfbench outputs.

Only items present in EVERY input dir are scored (common-item intersection),
so techniques run on different shard schedules stay strictly comparable.

Usage:
    python -m evals.public.compare_techniques \
        --label oneshot-glm=technique-oneshot-glm --label pipeline=technique-pipeline ...
"""
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
from typing import Dict, List

EVALS_OUTPUT = Path(__file__).resolve().parent.parent / "output"


def load_dir(base: str) -> Dict[str, dict]:
    """Merge items.jsonl from the base dir plus any -a/-b/-c shard dirs."""
    records: Dict[str, dict] = {}
    candidates = [EVALS_OUTPUT / base]
    candidates.extend(sorted(EVALS_OUTPUT.glob(f"{base}-*")))
    found = False
    for directory in candidates:
        path = directory / "items.jsonl"
        if not path.exists():
            continue
        found = True
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                records[f"{record['task']}/{record['id']}"] = record
    if not found:
        raise FileNotFoundError(f"no items.jsonl under {EVALS_OUTPUT} for '{base}'")
    return records


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def score(records: List[dict]) -> Dict[str, float]:
    ok = [r for r in records if not r.get("error") and "metrics" in r]
    return {
        "n": len(records),
        "scored": len(ok),
        "node_f1": mean([r["metrics"]["node"]["f1_score"] for r in ok]),
        "graph_f1": mean([r["metrics"]["graph_official"]["f1_score"] for r in ok]),
        "graph_mapped_f1": mean([r["metrics"]["graph_mapped"]["f1_score"] for r in ok]),
        "latency_s": mean([r.get("latency_s", 0.0) for r in ok]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label", action="append", required=True,
        help="label=dir (relative to evals/output or absolute)",
    )
    parser.add_argument("--output", type=str, default=str(EVALS_OUTPUT / "technique-comparison"))
    args = parser.parse_args()

    loaded = {label: load_dir(directory) for label, directory in
              (arg.split("=", 1) for arg in args.label)}
    common = set.intersection(*(set(records) for records in loaded.values()))
    if not common:
        print("no common items across inputs")
        return 1

    table = {label: score([records[key] for key in sorted(common)]) for label, records in loaded.items()}
    lines = [
        "# 编排技术横向对比（WorfBench 同题集）", "",
        f"- 共同题目数: {len(common)}（各技术完全相同的题目交集，node/graph 口径一致）",
        "- 节点匹配: char-bigram 余弦（官方 mpnet 口径的保守下界）", "",
        "| 技术 | 题数 | 评分 | Node F1 | Graph F1 | Graph F1 (mapped) | 平均耗时(s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, s in table.items():
        lines.append(
            f"| {label} | {s['scored']}/{s['n']} | {s['n'] - s['scored']} errors "
            f"| **{s['node_f1']:.3f}** | **{s['graph_f1']:.3f}** "
            f"| {s['graph_mapped_f1']:.3f} | {s['latency_s']:.0f} |"
        )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "comparison.json").write_text(
        json.dumps({"common_items": len(common), "techniques": table}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"common items: {len(common)}")
    print(f"{'technique':<22}{'scored':>9}{'nodeF1':>9}{'graphF1':>9}{'lat(s)':>8}")
    for label, s in table.items():
        print(f"{label:<22}{s['scored']:>4}/{s['n']:<4}{s['node_f1']:>9.3f}"
              f"{s['graph_f1']:>9.3f}{s['latency_s']:>8.0f}")
    print(f"report: {output_dir / 'comparison.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
