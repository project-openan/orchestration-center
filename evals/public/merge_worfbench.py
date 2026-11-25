# -*- coding: utf-8 -*-
"""Merge shard outputs of run_worfbench into a combined report.

Usage:
    python -m evals.public.merge_worfbench --shards a b c [--output DIR]
Shard dirs are expected at evals/output/worfbench-online-<shard>/items.jsonl
(or pass explicit paths). Prints a combined per-task table and writes
report.json / report.md into --output (default evals/output/worfbench-online).
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


def load_records(sources: List[str]) -> List[dict]:
    records: List[dict] = []
    for source in sources:
        path = Path(source)
        if not path.exists():
            path = EVALS_OUTPUT / f"worfbench-online-{source}" / "items.jsonl"
        if not path.exists():
            print(f"warning: shard not found, skipped: {source}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def aggregate(records: List[dict]) -> dict:
    ok = [r for r in records if not r.get("error")]
    result = {
        "total": len(records),
        "scored": len(ok),
        "errors": len(records) - len(ok),
    }
    for prefix in ("node", "graph_official", "graph_mapped"):
        for metric in ("precision", "recall", "f1_score"):
            key = f"{prefix}.{metric}"
            values = [r["metrics"][prefix][metric] for r in ok]
            result[key] = sum(values) / len(values) if values else 0.0
    latencies = [r.get("latency_s", 0.0) for r in records]
    result["avg_latency_s"] = sum(latencies) / len(latencies) if latencies else 0.0
    return result


def render(report: dict) -> str:
    lines = ["# WorfBench x OpenAN 意图→PSOP 规划评测（合并报告）", ""]
    meta = report.get("meta", {})
    if meta:
        lines.append(f"- 模型: {meta.get('model')}  模式: {meta.get('mode')}  "
                     f"抽样: 每域 {meta.get('per_task')} 条 (seed={meta.get('seed')})")
        lines.append(f"- 节点匹配: char-bigram 余弦 (阈值 {meta.get('threshold')}) — 官方为 mpnet 句向量，本结果为保守下界")
        lines.append("")
    lines.append("| 任务域 | 条数 | 错误 | Node F1 | Graph F1 (official) | Graph F1 (mapped) | 平均耗时(s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for task, bucket in report["tasks"].items():
        lines.append(
            f"| {task} | {bucket['scored']}/{bucket['total']} | {bucket['errors']} "
            f"| {bucket['node.f1_score']:.3f} | {bucket['graph_official.f1_score']:.3f} "
            f"| {bucket['graph_mapped.f1_score']:.3f} | {bucket['avg_latency_s']:.0f} |"
        )
    overall = report["overall"]
    lines.append(
        f"| **合计** | {overall['scored']}/{overall['total']} | {overall['errors']} "
        f"| **{overall['node.f1_score']:.3f}** | **{overall['graph_official.f1_score']:.3f}** "
        f"| **{overall['graph_mapped.f1_score']:.3f}** | {overall['avg_latency_s']:.0f} |"
    )
    lines.append("")
    lines.append("Node = LIS 序列匹配（枚举 gold 拓扑序取最优）；Graph = 最大权节点匹配 + 连通分量子图匹配。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", nargs="+", default=["a", "b", "c"])
    parser.add_argument("--output", type=str, default=str(EVALS_OUTPUT / "worfbench-online"))
    parser.add_argument("--meta", type=str, default=None, help="meta json path (mode/per_task/...)")
    args = parser.parse_args()

    records = load_records(args.shards)
    by_task: Dict[str, List[dict]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record)

    report = {
        "tasks": {task: aggregate(bucket) for task, bucket in sorted(by_task.items())},
        "overall": aggregate(records),
    }
    if args.meta and Path(args.meta).exists():
        report["meta"] = json.loads(Path(args.meta).read_text(encoding="utf-8-sig"))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(render(report) + "\n", encoding="utf-8")

    print(f"{'task':<14}{'done':>6}{'err':>4}{'nodeF1':>9}{'gOff':>8}{'gMap':>8}")
    for task, bucket in report["tasks"].items():
        print(
            f"{task:<14}{bucket['scored']:>4}/{bucket['total']:<3}"
            f"{bucket['errors']:>3}{bucket['node.f1_score']:>9.3f}"
            f"{bucket['graph_official.f1_score']:>8.3f}{bucket['graph_mapped.f1_score']:>8.3f}"
        )
    overall = report["overall"]
    print(
        f"{'TOTAL':<14}{overall['scored']:>4}/{overall['total']:<3}{overall['errors']:>3}"
        f"{overall['node.f1_score']:>9.3f}{overall['graph_official.f1_score']:>8.3f}"
        f"{overall['graph_mapped.f1_score']:>8.3f}"
    )
    print(f"report: {output_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
