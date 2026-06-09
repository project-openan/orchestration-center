"""
External API integration test script.
Usage: python scripts/test_external_api.py
Requires: backend + sample agents running
"""
import requests
import json
import time
import sys

BASE = "http://127.0.0.1:5001/api/v1"
PASS = 0
FAIL = 0


def check(resp, expected_status=200, label=""):
    global PASS, FAIL
    body = resp.text[:300]
    if resp.status_code == expected_status:
        PASS += 1
        print(f"  [PASS] {label}  status={resp.status_code}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  expected={expected_status} got={resp.status_code}")
        print(f"         body={body}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    global PASS, FAIL

    # ────────── 1. POST /orchestrate/sop ──────────
    section("1. POST /orchestrate/sop (JSON body)")

    resp = requests.post(
        f"{BASE}/orchestrate/sop",
        json={
            "sop_content": (
                "## RAN节能优化流程\n"
                "### 步骤1 意图探索与评估\n"
                "1. 发起RAN ES意图探索请求，获取指定意图目标的最佳可能值\n"
                "2. 分析当前网络负载现状，评估基站状态\n"
                "### 步骤2 意图生成与执行\n"
                "1. 根据探索报告生成RAN节能意图内容\n"
                "2. 执行RAN ES意图生命周期管理，落实节能策略\n"
                "### 步骤3 效果评估\n"
                "1. 评估不同RAN域节能效果并生成报告\n"
                "2. 根据评估结果调整RAN ES意图\n"
            ),
            "name": "RAN节能优化工作流",
        },
        timeout=120,
    )
    check(resp, 201, "SOP orchestrate (JSON)")
    if resp.status_code == 201:
        sop_result = resp.json()
        print(f"         workflow_id={sop_result.get('data', {}).get('id', 'N/A')}")
        print(f"         steps={len(sop_result.get('data', {}).get('steps', []))}")


    # ────────── 2. POST /orchestrate/intent ──────────
    section("2. POST /orchestrate/intent")

    resp = requests.post(
        f"{BASE}/orchestrate/intent",
        json={
            "intent": "诊断RAN侧网络故障，定位根因并执行恢复操作",
            "name": "RAN故障诊断",
        },
        timeout=120,
    )
    check(resp, 201, "Intent orchestrate")
    intent_psop_id = None
    if resp.status_code == 201:
        data = resp.json().get("data", {})
        intent_psop_id = data.get("id")
        print(f"         workflow_id={intent_psop_id}")
        print(f"         steps={len(data.get('steps', []))}")


    # ────────── 3. POST /orchestrate/search ──────────
    section("3. POST /orchestrate/search")

    resp = requests.post(
        f"{BASE}/orchestrate/search",
        json={"intent": "RAN节能和故障诊断", "top_n": 5},
        timeout=60,
    )
    check(resp, 200, "Search workflows")
    if resp.status_code == 200:
        results = resp.json().get("data", [])
        print(f"         found {len(results)} workflow(s)")
        for r in results:
            print(f"           - {r.get('name')}  ({r.get('workflow_id', '')[:8]}...)")


    # ────────── 3.5 GET /orchestrate/psop/{id} ──────────
    section("3.5. GET /orchestrate/psop/{psop_id}")

    if intent_psop_id:
        resp = requests.get(f"{BASE}/orchestrate/psop/{intent_psop_id}", timeout=30)
        check(resp, 200, f"Get PSOP by ID ({intent_psop_id[:8]}...)")
        if resp.status_code == 200:
            psop = resp.json().get("data", {})
            print(f"         name={psop.get('name')} steps={len(psop.get('steps',[]))}")
    else:
        print("  [SKIP] No PSOP ID available")


    # ────────── 4. POST /orchestrate/execute (SSE) ──────────
    section("4. POST /orchestrate/execute (SSE stream)")

    resp = requests.post(
        f"{BASE}/orchestrate/execute?lang=zh",
        json={"task": "诊断RAN网络故障并生成分析报告"},
        stream=True,
        timeout=300,
    )
    check(resp, 200, "Execute auto (SSE)")

    execute_psop_id = None
    if resp.status_code == 200:
        print(f"         SSE stream started, receiving events...")
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
                etype = event.get("type", "?")
                if etype in ("start", "complete", "error", "close"):
                    print(f"         event: {etype}")
                elif etype == "psop_update":
                    psop = event.get("data", {}).get("psop", {})
                    if isinstance(psop, str):
                        psop = json.loads(psop)
                    execute_psop_id = psop.get("id", execute_psop_id)
            except Exception:
                pass
            if event.get("type") in ("complete", "error", "close"):
                break
        print(f"         psop_id={execute_psop_id}")


    # ────────── 5. GET /orchestrate/execute/{id} (SSE) ──────────
    section("5. GET /orchestrate/execute/{psop_id} (SSE stream)")

    if intent_psop_id:
        resp = requests.get(
            f"{BASE}/orchestrate/execute/{intent_psop_id}?lang=zh&user_intent=执行诊断",
            stream=True,
            timeout=300,
        )
        check(resp, 200, f"Execute by ID ({intent_psop_id[:8]}...)")
        if resp.status_code == 200:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                    if event.get("type") in ("complete", "error", "close"):
                        print(f"         event: {event.get('type')}")
                        break
                except Exception:
                    pass
    else:
        print("  [SKIP] No PSOP ID from intent orchestration")


    # ────────── 6. GET /executions ──────────
    section("6. GET /executions (list)")

    resp = requests.get(f"{BASE}/executions", timeout=30)
    check(resp, 200, "List executions")
    if resp.status_code == 200:
        records = resp.json().get("data", [])
        print(f"         found {len(records)} execution record(s)")
        for r in records[:3]:
            print(f"           - {r.get('psop_name','?')}  status={r.get('status')}")


    # ────────── 7. GET /executions/{id} ──────────
    section("7. GET /executions/{execution_id}")

    resp = requests.get(f"{BASE}/executions/nonexistent-id", timeout=30)
    check(resp, 404, "Get execution (not found)")

    if resp.status_code == 404:
        body = resp.json()
        print(f"         code={body.get('code')} status={body.get('status')}")


    # ────────── Summary ──────────
    section("Summary")
    total = PASS + FAIL
    print(f"  Passed: {PASS}/{total}")
    print(f"  Failed: {FAIL}/{total}")
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
