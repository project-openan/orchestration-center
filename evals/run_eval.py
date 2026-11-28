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

"""CLI runner for the intent-to-PSOP planning evaluation set.

Modes:
- gold (default): harness self-check — every gold reference PSOP must pass its
  case requirements (100%); ``--selftest`` additionally asserts that built-in
  single-aspect mutations of gold workflows are all rejected.
- pregen: score externally generated PSOP files against the case set
  (``--psop-dir`` with ``<case_id>.json`` files, or ``--psop-file`` +
  ``--case-id``). Fully offline.
- online: drive ``IntentPsopGenerator`` with the configured chat LLM
  (``etc/config/models.yaml``) for each case, then score; ``--k`` replicates
  each case k times and reports pass^k reliability (tau-bench style).

Usage:
    python -m evals.run_eval --mode gold --selftest
    python -m evals.run_eval --mode pregen --psop-dir out/psops
    python -m evals.run_eval --mode online --k 3 --limit 5
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from orchestrate.core.model.psop import PSOP

from evals.scoring.case_model import (
    DIMENSIONS,
    EVALS_DATA_DIR,
    AgentPool,
    EvalCase,
    load_cases,
    load_pool,
    validate_case_against_pool,
)
from evals.scoring.planner_scorer import CaseReport, PlannerScorer
from evals.scoring.report import aggregate, render_markdown
from evals.scoring.selftest import run_selftest

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def load_pools(cases: List[EvalCase]) -> Dict[str, AgentPool]:
    pools: Dict[str, AgentPool] = {}
    for pool_name in {case.agent_pool for case in cases}:
        pools[pool_name] = load_pool(pool_name)
    return pools


def validate_dataset(cases: List[EvalCase], pools: Dict[str, AgentPool]) -> List[str]:
    """Dataset QA: pool references, skill ownership, gold file existence."""
    errors: List[str] = []
    for case in cases:
        pool = pools.get(case.agent_pool)
        if pool is None:
            errors.append(f"{case.id}: unknown agent pool '{case.agent_pool}'")
            continue
        errors.extend(validate_case_against_pool(case, pool))
        if case.gold_psop_file:
            gold_path = EVALS_DATA_DIR / case.gold_psop_file
            if not gold_path.exists():
                errors.append(f"{case.id}: gold psop file missing: {gold_path}")
    return errors


def load_psop_file(path: Path) -> tuple:
    """Load a PSOP JSON file; returns (psop_or_None, parse_error_or_None)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return PSOP.model_validate(payload), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def score_all(
    cases: List[EvalCase], pools: Dict[str, AgentPool], outputs: Dict[str, tuple]
) -> List[CaseReport]:
    """Score a mapping case_id -> (psop_or_None, parse_error_or_None)."""
    reports: List[CaseReport] = []
    for case in cases:
        psop, parse_error = outputs.get(case.id, (None, "no planner output supplied"))
        scorer = PlannerScorer(case, pools[case.agent_pool])
        reports.append(scorer.score(psop, parse_error))
    return reports


def write_report(reports: List[CaseReport], output_dir: Path, title: str) -> Path:
    summary = aggregate(reports)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary, title=title))
    return md_path


def print_summary(reports: List[CaseReport]) -> None:
    summary = aggregate(reports)
    print("")
    print("=== 评测汇总 ===")
    print(f"用例总数: {summary['total']}  通过: {summary['passed']}  "
          f"通过率: {summary['pass_rate']:.1%}")
    print("")
    print(f"{'维度':<24}{'用例':>6}{'通过':>6}{'通过率':>10}")
    for dimension, bucket in summary["by_dimension"].items():
        label = DIMENSIONS.get(dimension, dimension)
        print(f"{label:<24}{bucket['total']:>6}{bucket['passed']:>6}"
              f"{bucket['pass_rate']:>10.1%}")
    if summary.get("metric_means"):
        print("")
        print("分项指标均值（域内用例）:")
        for name, value in summary["metric_means"].items():
            print(f"  {name:<22}{value:.3f}")
    if summary["failed_cases"]:
        print("")
        print("未通过用例:")
        for failed in summary["failed_cases"]:
            print(f"  [{failed['case_id']}] " + "; ".join(failed["failures"][:4]))


# ---------------------------------------------------------------------------
# gold mode
# ---------------------------------------------------------------------------


def run_gold(args) -> int:
    cases = load_cases(args.cases)
    pools = load_pools(cases)
    errors = validate_dataset(cases, pools)
    if errors:
        print("数据集校验失败:")
        for error in errors:
            print(f"  - {error}")
        return 1

    gold_cases = [case for case in cases if case.gold_psop_file]
    outputs: Dict[str, tuple] = {}
    for case in gold_cases:
        psop, parse_error = load_psop_file(EVALS_DATA_DIR / case.gold_psop_file)
        outputs[case.id] = (psop, parse_error)
    reports = score_all(gold_cases, pools, outputs)

    failures = [report for report in reports if not report.passed]
    print(f"gold 自检: {len(gold_cases) - len(failures)}/{len(gold_cases)} 参考答案通过")
    if failures:
        for report in failures:
            print(f"  [{report.case_id}] " + "; ".join(report.failures[:6]))

    if args.selftest:
        cases_by_id = {case.id: case for case in cases}
        problems = run_selftest(cases_by_id, pools)
        print(f"变异自检: {'全部拒绝' if not problems else f'{len(problems)} 项未拒绝'}")
        for problem in problems:
            print(f"  - {problem}")
        failures.extend(problems)

    if failures:
        print_summary(reports)
        return 1
    print_summary(reports)
    print("\ngold 自检通过：评分器对全部参考答案判定通过，且全部变异被拒绝。")
    return 0


# ---------------------------------------------------------------------------
# pregen mode
# ---------------------------------------------------------------------------


def run_pregen(args) -> int:
    cases = load_cases(args.cases)
    pools = load_pools(cases)
    by_id = {case.id: case for case in cases}

    outputs: Dict[str, tuple] = {}
    consumed: set = set()
    if args.psop_file:
        if not args.case_id:
            print("--psop-file 需要配合 --case-id")
            return 2
        if args.case_id not in by_id:
            print(f"未知用例: {args.case_id}")
            return 2
        outputs[args.case_id] = load_psop_file(Path(args.psop_file))
        consumed.add(args.case_id)
    elif args.psop_dir:
        psop_dir = Path(args.psop_dir)
        if not psop_dir.is_dir():
            print(f"目录不存在: {psop_dir}")
            return 2
        for path in sorted(psop_dir.glob("*.json")):
            case_id = path.stem
            if case_id not in by_id:
                print(f"警告: {path.name} 不匹配任何用例 id，跳过")
                continue
            outputs[case_id] = load_psop_file(path)
            consumed.add(case_id)
    else:
        print("pregen 模式需要 --psop-dir 或 --psop-file/--case-id")
        return 2

    selected = [by_id[case_id] for case_id in sorted(consumed)]
    reports = score_all(selected, pools, outputs)
    md_path = write_report(
        reports, Path(args.output) if args.output else DEFAULT_OUTPUT_ROOT / "pregen",
        title="意图→PSOP 编排规划评测报告（pregen）",
    )
    print_summary(reports)
    print(f"\n报告已写入: {md_path}")
    return 1 if any(not report.passed for report in reports) else 0


# ---------------------------------------------------------------------------
# online mode
# ---------------------------------------------------------------------------


def _pool_agent_cards(pool: AgentPool, agent_names):
    """Build a2a AgentCard objects for the case's visible agents (online mode)."""
    from a2a.types import AgentCard
    from google.protobuf.json_format import Parse

    from orchestrate.agentcard_loader import _normalize_agent_dict
    from orchestrate.validation.sandbox_validator import TASK_T_URI

    cards = []
    for index, agent in enumerate(pool.agents):
        if agent.name not in agent_names:
            continue
        payload = agent.model_dump()
        payload.setdefault("version", "1.0.0")
        capabilities = payload.setdefault("capabilities", {"streaming": True})
        extensions = capabilities.setdefault("extensions", [])
        if not any(
            isinstance(ext, dict) and ext.get("uri") == TASK_T_URI for ext in extensions
        ):
            extensions.append({
                "uri": TASK_T_URI,
                "description": "Task-T structured task extension (eval pools)",
                "required": False,
            })
        payload.setdefault(
            "defaultInputModes", ["application/json", "text/plain"]
        )
        payload.setdefault(
            "defaultOutputModes", ["application/json", "text/plain"]
        )
        payload.setdefault(
            "supportedInterfaces",
            [{
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
                "url": f"https://127.0.0.1:{26500 + index}/a2a/json",
                "tenant": "",
            }],
        )
        cards.append(Parse(json.dumps(payload, ensure_ascii=False), AgentCard()))
    return cards


def run_online(args) -> int:
    from orchestrate.core.intent_psop_generator import (
        IntentPsopGenerator,
        IntentWorkflowGeneratorError,
    )

    cases = load_cases(args.cases)
    pools = load_pools(cases)
    errors = validate_dataset(cases, pools)
    if errors:
        print("数据集校验失败:")
        for error in errors:
            print(f"  - {error}")
        return 1

    if args.dimensions:
        wanted = {d.strip() for d in args.dimensions.split(",") if d.strip()}
        unknown = wanted - set(DIMENSIONS)
        if unknown:
            print(f"未知维度: {sorted(unknown)}")
            return 2
        cases = [case for case in cases if case.dimension in wanted]
    if args.limit:
        cases = cases[: args.limit]

    try:
        generator = IntentPsopGenerator()
    except Exception as exc:
        print(
            "online 模式需要已配置的对话大模型（etc/config/models.yaml 或 "
            f"LLM_CONFIG_FILE）：{exc}"
        )
        return 2

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_ROOT / "online"
    psop_dir = output_dir / "psops"
    psop_dir.mkdir(parents=True, exist_ok=True)

    reports: List[CaseReport] = []
    pass1_count = 0
    passk_count = 0
    for case in cases:
        cards = _pool_agent_cards(pools[case.agent_pool], set(case.agents))
        try_reports = []
        for attempt in range(args.k):
            parse_error: Optional[str] = None
            psop = None
            try:
                psop = generator.generate_psop_from_intent(
                    case.intent, cards, workflow_name=f"{case.id}#try{attempt + 1}"
                )
                psop.user_intent = case.intent
            except IntentWorkflowGeneratorError as exc:
                parse_error = f"generation failed: {exc}"
            if psop is not None:
                with open(
                    psop_dir / f"{case.id}-try{attempt + 1}.json", "w", encoding="utf-8"
                ) as handle:
                    handle.write(psop.model_dump_json(indent=2))
            scorer = PlannerScorer(case, pools[case.agent_pool])
            try_reports.append(scorer.score(psop, parse_error))
        reports.extend(try_reports)
        if all(report.passed for report in try_reports):
            passk_count += 1
        if any(report.passed for report in try_reports):
            pass1_count += 1
        status = "PASS^k" if all(r.passed for r in try_reports) else (
            "PASS^1" if any(r.passed for r in try_reports) else "FAIL"
        )
        print(f"[{case.id}] {status} ({len(try_reports)} tries)")

    md_path = write_report(
        reports, output_dir, title="意图→PSOP 编排规划评测报告（online）"
    )
    print_summary(reports)
    print("")
    print(f"pass^1: {pass1_count}/{len(cases)}  pass^k(k={args.k}): {passk_count}/{len(cases)}")
    print(f"报告已写入: {md_path}")
    return 0


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run_eval",
        description="OpenAN 意图→PSOP 编排规划评测集运行器",
    )
    parser.add_argument(
        "--mode",
        choices=["gold", "pregen", "online"],
        default="gold",
        help="gold=参考答案自检（默认）；pregen=离线评分已生成的 PSOP；online=调用真实 LLM 评测",
    )
    parser.add_argument("--cases", type=str, default=None, help="用例集路径（默认 evals/data/cases.jsonl）")
    parser.add_argument("--selftest", action="store_true", help="gold 模式附加变异自检")
    parser.add_argument("--psop-dir", type=str, default=None, help="pregen: 含 <case_id>.json 的目录")
    parser.add_argument("--psop-file", type=str, default=None, help="pregen: 单个 PSOP 文件")
    parser.add_argument("--case-id", type=str, default=None, help="pregen: 单文件对应的用例 id")
    parser.add_argument("--k", type=int, default=1, help="online: 每条用例重复次数（pass^k）")
    parser.add_argument("--limit", type=int, default=None, help="online: 最多评测前 N 条用例")
    parser.add_argument("--dimensions", type=str, default=None, help="online: 逗号分隔的维度过滤")
    parser.add_argument("--output", type=str, default=None, help="报告输出目录")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "gold":
        return run_gold(args)
    if args.mode == "pregen":
        return run_pregen(args)
    return run_online(args)


if __name__ == "__main__":
    sys.exit(main())
