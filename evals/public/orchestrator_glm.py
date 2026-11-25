# -*- coding: utf-8 -*-
"""GLM-gateway orchestrator for the remaining three benches (option B)."""
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from evals.public.gateway_env import load_gateway_key  # noqa: E402

load_gateway_key()
GATEWAY_KEY = os.environ.get("LANQU_GATEWAY_API_KEY", "")
if not GATEWAY_KEY:
    raise SystemExit("gateway key unavailable")
GATEWAY_BASE = "https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1"
GATEWAY_MODEL = "glm-5.3-flash"

WAVES = [
    {"name": "G1-nestful", "bench": "nestful", "target": 1861, "shards": 12,
     "fw_shards": 6, "per_task": "100000", "outbase": "nestful-glm",
     "items": str(OUT / "full-items" / "items-nestful.jsonl"), "max_hours": 6},
    {"name": "G2-workflowbench", "bench": "workflowbench", "target": 50, "shards": 6,
     "fw_shards": 6, "per_task": "100000", "outbase": "workflowbench-glm",
     "items": str(OUT / "full-items" / "items-workflowbench.jsonl"), "max_hours": 1},
    {"name": "G3-taskbench", "bench": "taskbench", "target": 17331, "shards": 24,
     "fw_shards": 12, "per_task": "100000", "outbase": "taskbench-glm",
     "items": str(OUT / "full-items" / "items-taskbench.jsonl"), "max_hours": 24},
]


def log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG / "orchestrator-glm.log", "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def count_json(directory):
    if not Path(directory).exists():
        return 0
    return len(list(Path(directory).glob("*.json")))


def alive_processes(pattern):
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match '" + pattern + "' } | "
        "Measure-Object | Select-Object -ExpandProperty Count"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=60)
    try:
        return int(result.stdout.strip() or 0)
    except Exception:
        return -1


def shard_pids(pattern):
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match '" + pattern + "' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=60)
    return [int(x) for x in result.stdout.split() if x.strip().isdigit()]


def launch_wave(wave):
    bench, shards = wave["bench"], wave["shards"]
    for index in range(shards):
        args = [
            PY, "-m", "evals.public.run_worfbench", "--bench", bench,
            "--mode", "online", "--technique", "oneshot",
            "--per-task", wave["per_task"],
            "--shard-count", str(shards), "--shard-index", str(index),
            "--resume",
            "--output", str(OUT / wave["outbase"] / f"on{index}"),
        ]
        log(f"  launch OpenAN shard {index + 1}/{shards}")
        openan_env = dict(os.environ)
        openan_env["EVAL_DISABLE_FILE_LOG"] = "1"
        subprocess.Popen(args, cwd=str(ROOT), env=openan_env,
                         stdout=open(LOG / f"glm-{bench}-openan-s{index}.log", "ab"),
                         stderr=open(LOG / f"glm-{bench}-openan-s{index}.err.log", "ab"),
                         creationflags=subprocess.CREATE_NO_WINDOW)
    for framework in FRAMEWORKS:
        for index in range(wave["fw_shards"]):
            args = [str(FPY), GEN, "--framework", framework,
                    "--items", wave["items"],
                    "--out", str(OUT / "framework-compare" / framework / f"plans-{bench}"),
                    "--shard-count", str(wave["fw_shards"]), "--shard-index", str(index)]
            env = dict(os.environ)
            env.update({
                "OPENAI_BASE_URL": GATEWAY_BASE,
                "OPENAI_API_KEY": GATEWAY_KEY,
                "FW_LLM_BASE_URL": GATEWAY_BASE,
                "FW_LLM_MODEL": GATEWAY_MODEL,
                "FW_LLM_API_KEY": GATEWAY_KEY,
                "PYTHONIOENCODING": "utf-8",
            })
            log(f"  launch {framework} shard {index + 1}/{wave['fw_shards']}")
            subprocess.Popen(args, cwd=str(ROOT), env=env,
                             stdout=open(LOG / f"glm-{bench}-{framework}-s{index}.log", "ab"),
                             stderr=open(LOG / f"glm-{bench}-{framework}-s{index}.err.log", "ab"),
                             creationflags=subprocess.CREATE_NO_WINDOW)


def score_wave(wave):
    bench, outbase, shards = wave["bench"], wave["outbase"], wave["shards"]
    merged = OUT / outbase / "psops-merged"
    merged.mkdir(parents=True, exist_ok=True)
    for index in range(shards):
        src = OUT / outbase / f"on{index}" / "psops"
        if Path(src).exists():
            for psop in Path(src).glob("*.json"):
                (merged / psop.name).write_bytes(psop.read_bytes())
    subprocess.run(
        [PY, "-m", "evals.public.run_worfbench", "--bench", bench, "--mode", "pregen",
         "--psop-dir", str(merged), "--output", str(OUT / outbase / "score")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
    log(f"{bench}: OpenAN pregen scored ({count_json(merged)})")
    for framework in FRAMEWORKS:
        subprocess.run(
            [PY, "-m", "evals.public.framework_exchange", "--convert", "--bench", bench,
             "--framework", framework, "--output", str(OUT / "framework-compare")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
        subprocess.run(
            [PY, "-m", "evals.public.run_worfbench", "--bench", bench, "--mode", "pregen",
             "--psop-dir", str(OUT / "framework-compare" / framework / f"psops-{bench}"),
             "--output", str(OUT / "framework-compare" / framework / f"score-{bench}")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
    log(f"{bench}: frameworks scored")


def run_wave(wave):
    bench, target = wave["bench"], wave["target"]
    outbase, fw_shards = wave["outbase"], wave["fw_shards"]
    deadline = time.time() + wave["max_hours"] * 3600
    openan_pattern = outbase
    fw_pattern = f"plans-{bench}"
    if alive_processes(openan_pattern) == 0:
        launch_wave(wave)
    else:
        log(f"{bench}: shards alive; attaching")
    stall_polls = 0
    last_total = -1
    while time.time() < deadline:
        psop_total = sum(count_json(OUT / outbase / f"on{i}" / "psops") for i in range(wave["shards"]))
        fw_total = sum(count_json(OUT / "framework-compare" / fw / f"plans-{bench}") for fw in FRAMEWORKS)
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
            log(f"{bench}: OpenAN dead at {psop_total}; relaunch (resume)")
            launch_wave(wave)
        if fw_alive == 0 and fw_total < target * len(FRAMEWORKS):
            log(f"{bench}: frameworks dead at {fw_total}; relaunch (resume)")
            launch_wave(wave)
        if stall_polls >= 4 and (openan_alive > 0 or fw_alive > 0):
            log(f"{bench}: stalled {stall_polls} polls; force restart")
            for pid in shard_pids(openan_pattern) + shard_pids(fw_pattern):
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
            launch_wave(wave)
            stall_polls = 0
        time.sleep(300)


def main():
    log("===== GLM orchestrator started (remaining benches) =====")
    for wave in WAVES:
        log(f"--- {wave['name']} (target {wave['target']}) ---")
        run_wave(wave)
        score_wave(wave)
    log("===== GLM waves done =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
