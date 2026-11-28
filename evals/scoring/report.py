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

"""Aggregate case reports into a summary and render a Markdown report."""

from typing import Dict, List

from evals.scoring.case_model import DIMENSIONS
from evals.scoring.planner_scorer import CaseReport

IN_SCOPE_METRICS = [
    "topology_valid",
    "skill_recall",
    "skill_precision",
    "agent_consistency",
    "structure_pass",
    "order_pass",
    "capability_coverage",
]


def aggregate(reports: List[CaseReport]) -> dict:
    in_scope = [report for report in reports if not report.out_of_scope]
    out_of_scope = [report for report in reports if report.out_of_scope]
    by_dimension: Dict[str, dict] = {}
    for report in reports:
        bucket = by_dimension.setdefault(
            report.dimension, {"total": 0, "passed": 0, "pass_rate": 0.0}
        )
        bucket["total"] += 1
        bucket["passed"] += int(report.passed)

    metric_sums: Dict[str, float] = {}
    metric_counts: Dict[str, int] = {}
    for report in in_scope:
        for name, value in report.metrics.items():
            metric_sums[name] = metric_sums.get(name, 0.0) + float(value)
            metric_counts[name] = metric_counts.get(name, 0) + 1
    metric_means = {
        name: (metric_sums[name] / metric_counts[name])
        for name in sorted(metric_sums)
        if metric_counts[name]
    }

    for bucket in by_dimension.values():
        bucket["pass_rate"] = bucket["passed"] / bucket["total"] if bucket["total"] else 0.0

    return {
        "total": len(reports),
        "passed": sum(int(report.passed) for report in reports),
        "pass_rate": (
            sum(int(report.passed) for report in reports) / len(reports) if reports else 0.0
        ),
        "in_scope": {
            "total": len(in_scope),
            "passed": sum(int(report.passed) for report in in_scope),
        },
        "out_of_scope": {
            "total": len(out_of_scope),
            "refused": sum(int(report.passed) for report in out_of_scope),
        },
        "by_dimension": by_dimension,
        "metric_means": metric_means,
        "failed_cases": [
            {
                "case_id": report.case_id,
                "dimension": report.dimension,
                "parse_error": report.parse_error,
                "metrics": report.metrics,
                "failures": report.failures,
            }
            for report in reports
            if not report.passed
        ],
    }


def render_markdown(summary: dict, title: str = "意图→PSOP 编排规划评测报告") -> str:
    lines: List[str] = [f"# {title}", ""]

    # per-dimension table
    lines.append("| 维度 | 用例数 | 通过 | 通过率 |")
    lines.append("|---|---|---|---|")
    for dimension, bucket in summary["by_dimension"].items():
        label = DIMENSIONS.get(dimension, dimension)
        lines.append(
            f"| {label} ({dimension}) | {bucket['total']} | {bucket['passed']} "
            f"| {bucket['pass_rate']:.1%} |"
        )
    lines.append(
        f"| **合计** | {summary['total']} | {summary['passed']} | {summary['pass_rate']:.1%} |"
    )
    lines.append("")

    # metric means (in-scope)
    if summary.get("metric_means"):
        lines.append("## 分项指标均值（域内用例）")
        lines.append("")
        lines.append("| 指标 | 均值 |")
        lines.append("|---|---|")
        for name in IN_SCOPE_METRICS:
            if name in summary["metric_means"]:
                lines.append(f"| {name} | {summary['metric_means'][name]:.3f} |")
        lines.append("")

    refusals = summary.get("out_of_scope", {})
    if refusals.get("total"):
        lines.append(
            f"## 越界拒答：{refusals['refused']}/{refusals['total']} 正确拒绝"
        )
        lines.append("")

    if summary.get("failed_cases"):
        lines.append("## 未通过用例明细")
        lines.append("")
        for failed in summary["failed_cases"]:
            lines.append(f"### {failed['case_id']} ({failed['dimension']})")
            lines.append("")
            if failed.get("parse_error"):
                lines.append(f"- 解析错误: {failed['parse_error']}")
            for failure in failed["failures"]:
                lines.append(f"- {failure}")
            lines.append("")

    return "\n".join(lines)
