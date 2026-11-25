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

"""Detached orchestrator for the full-coverage benchmark runs.

Self-healing: polls output counts every 5 minutes; OpenAN and framework shard
families are tracked independently — when one family has no live process and
its target is unmet, its shards are relaunched (resume skips finished items).
Stalled-but-alive shards are force-restarted after repeated stall polls.

Run detached:
    Start-Process python orchestrator.py -WindowStyle Hidden
Logs: evals/output/full-run-logs/orchestrator.log
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\OpenAN\orchestration-center")
OUT = ROOT / "evals" / "output"
LOG = OUT / "full-run-logs"
LOG.mkdir(parents=True, exist_ok=True)
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
FPY = Path(r"D:\OpenAN\framework-venv\Scripts\python.exe")
GEN = str(ROOT / "evals" / "public" / "frameworks" / "gen_plans.py")
FRAMEWORKS = ["langgraph", "agents", "ag2"]

WAVES = [
    {"name": "W1-worfbench", "bench": "worfbench", "target": 2146, "shards": 12,
     "fw_shards": 6, "per_task": "100000", "outbase": "worfbench-full",
     "items": str(OUT / "framework-compare" / "items-worfbench.jsonl"), "max_hours": 3},
    {"name": "W2-nestful", "bench": "nestful", "target": 1861, "shards": 12,
     "fw_shards": 6, "per_task": "100000", "outbase": "nestful-full",
     "items": str(OUT / "full-items" / "items-nestful.jsonl"), "max_hours": 2},
    {"name": "W3-workflowbench", "bench": "workflowbench", "target": 50, "shards": 6,
     "fw_shards": 6, "per_task": "100000", "outbase": "workflowbench-full",
     "items": str(OUT / "full-items" / "items-workflowbench.jsonl"), "max_hours": 1},
    {"name": "W4-taskbench", "bench": "taskbench", "target": 17331, "shards": 24,
     "fw_shards": 12, "per_task": "100000", "outbase": "taskbench-full",
     "items": str(OUT / "full-items" / "items-taskbench.jsonl"), "max_hours": 30},
]

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-flash"


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG / "orchestrator.log", "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def count_json(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.json")))


def alive_processes(pattern: str) -> int:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match '" + pattern + "' } | "
        "Measure-Object | Select-Object -ExpandProperty Count"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
        return int(result.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return -1  # unknown: treat as alive (never relaunch blindly)


def shard_pids(pattern: str) -> list:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match '" + pattern + "' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
        return [int(x) for x in result.stdout.split() if x.strip().isdigit()]
    except Exception:  # noqa: BLE001
        return []


def kill_pids(pids: list) -> None:
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)


def popen(args: list, stdout: Path, stderr: Path, env: dict = None) -> None:
    subprocess.Popen(
        args, cwd=str(ROOT), env=env,
        stdout=open(stdout, "ab"), stderr=open(stderr, "ab"),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def launch_openan_shards(wave: dict) -> None:
    bench, shards = wave["bench"], wave["shards"]
    for index in range(shards):
        args = [
            PY, "-m", "evals.public.run_worfbench",
            "--bench", bench, "--mode", "online", "--technique", "oneshot",
            "--per-task", wave["per_task"],
            "--shard-count", str(shards), "--shard-index", str(index),
            "--resume",
            "--models-config", str(ROOT / "evals" / "public" / "models_deepseek.yaml"),
            "--env-key-file", str(ROOT / ".env"), "--env-key-var", "DEEPSEEK_API_KEY",
            "--output", str(OUT / wave["outbase"] / f"on{index}"),
        ]
        log(f"  launch OpenAN shard {index + 1}/{shards}")
        popen(args, LOG / f"{bench}-openan-s{index}.log", LOG / f"{bench}-openan-s{index}.err.log")


def launch_framework_shards(wave: dict) -> None:
    bench, fw_shards = wave["bench"], wave["fw_shards"]
    for framework in FRAMEWORKS:
        for index in range(fw_shards):
            args = [
                str(FPY), GEN, "--framework", framework,
                "--items", wave["items"],
                "--out", str(OUT / "framework-compare" / framework / f"plans-{bench}"),
                "--shard-count", str(fw_shards), "--shard-index", str(index),
            ]
            log(f"  launch {framework} shard {index + 1}/{fw_shards}")
            env = dict(os.environ)
            env.update({
                "OPENAI_BASE_URL": DEEPSEEK_BASE,
                "OPENAI_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
                "FW_LLM_BASE_URL": DEEPSEEK_BASE,
                "FW_LLM_MODEL": DEEPSEEK_MODEL,
                "FW_LLM_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
                "PYTHONIOENCODING": "utf-8",
            })
            popen(args, LOG / f"{bench}-{framework}-s{index}.log",
                  LOG / f"{bench}-{framework}-s{index}.err.log", env=env)


def run_wave(wave: dict) -> None:
    bench, target = wave["bench"], wave["target"]
    outbase, fw_shards = wave["outbase"], wave["fw_shards"]
    deadline = time.time() + wave["max_hours"] * 3600
    openan_pattern = wave["outbase"].replace("\\", "\\\\")
    fw_pattern = f"plans-{bench}"

    if alive_processes(openan_pattern) == 0:
        launch_openan_shards(wave)
    else:
        log(f"{bench}: OpenAN shards alive; attaching")
    if alive_processes(fw_pattern) == 0:
        launch_framework_shards(wave)
    else:
        log(f"{bench}: framework shards alive; attaching")

    stall_polls = 0
    last_total = -1
    while time.time() < deadline:
        psop_total = sum(
            count_json(OUT / outbase / f"on{index}" / "psops")
            for index in range(wave["shards"])
        )
        fw_total = sum(
            count_json(OUT / "framework-compare" / framework / f"plans-{bench}")
            for framework in FRAMEWORKS
        )
        log(f"{bench}: OpenAN={psop_total}/{target} frameworks={fw_total}/{target * len(FRAMEWORKS)}")
        if psop_total >= target and fw_total >= target * len(FRAMEWORKS):
            log(f"{bench}: wave complete")
            return
        openan_alive = alive_processes(openan_pattern)
        fw_alive = alive_processes(fw_pattern)
        total_now = psop_total + fw_total
        stall_polls = stall_polls + 1 if total_now == last_total else 0
        last_total = total_now
        if openan_alive == 0 and psop_total < target:
            log(f"{bench}: OpenAN dead at {psop_total}/{target}; relaunch (resume)")
            launch_openan_shards(wave)
        if fw_alive == 0 and fw_total < target * len(FRAMEWORKS):
            log(f"{bench}: frameworks dead at {fw_total}; relaunch (resume)")
            launch_framework_shards(wave)
        if stall_polls >= 4 and (openan_alive > 0 or fw_alive > 0):
            log(f"{bench}: stalled {stall_polls} polls; force-restarting shards")
            kill_pids(shard_pids(openan_pattern) + shard_pids(fw_pattern))
            launch_openan_shards(wave)
            launch_framework_shards(wave)
            stall_polls = 0
        time.sleep(300)


def score_wave(wave: dict) -> None:
    bench, outbase, shards = wave["bench"], wave["outbase"], wave["shards"]
    merged = OUT / outbase / "psops-merged"
    merged.mkdir(parents=True, exist_ok=True)
    for index in range(shards):
        src = OUT / outbase / f"on{index}" / "psops"
        if src.exists():
            for psop in src.glob("*.json"):
                (merged / psop.name).write_bytes(psop.read_bytes())
    subprocess.run(
        [PY, "-m", "evals.public.run_worfbench", "--bench", bench, "--mode", "pregen",
         "--psop-dir", str(merged), "--output", str(OUT / outbase / "score")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=3600,
    )
    log(f"{bench}: OpenAN pregen scored ({count_json(merged)} psops)")
    for framework in FRAMEWORKS:
        subprocess.run(
            [PY, "-m", "evals.public.framework_exchange", "--convert", "--bench", bench,
             "--framework", framework, "--output", str(OUT / "framework-compare")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3600,
        )
        subprocess.run(
            [PY, "-m", "evals.public.run_worfbench", "--bench", bench, "--mode", "pregen",
             "--psop-dir", str(OUT / "framework-compare" / framework / f"psops-{bench}"),
             "--output", str(OUT / "framework-compare" / framework / f"score-{bench}")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3600,
        )
    log(f"{bench}: frameworks scored")


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from evals.public.gateway_env import load_env_var_from_file

    if not load_env_var_from_file(ROOT / ".env", "DEEPSEEK_API_KEY"):
        log("FATAL: DEEPSEEK_API_KEY not found in repo .env")
        return 2
    log("planner: deepseek-flash (direct API) for ALL planners; GLM artifacts archived")
    log("===== full-coverage orchestrator started =====")
    for wave in WAVES:
        log(f"--- {wave['name']} (target {wave['target']}) ---")
        run_wave(wave)
        score_wave(wave)
    log("===== all waves done =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
