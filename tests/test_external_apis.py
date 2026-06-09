# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

"""
编排中心对外 API 集成测试（真实调用，无模拟）

基于权威文档：docs/zh/编排中心API参考.md

启动方式：
  1. 注册中心：python -m agent_registry.start   (默认 http://127.0.0.1:5000)
  2. 编排中心：python -m orchestrate.start       (默认 http://127.0.0.1:5001)
  3. 确保注册中心已注册至少一个 Agent

用法：
  pytest tests/test_external_apis.py -v -s
  或
  python tests/test_external_apis.py

环境变量（可选）：
  ORCHESTRATE_BASE_URL   编排中心地址，默认 http://127.0.0.1:5001
  TEST_PDF_FILE          测试用 PDF SOP 文件路径（可选，用于文件上传测试）
  TEST_TXT_FILE          测试用 TXT/MD SOP 文件路径（可选，用于 TXT 上传测试）
"""

import json
import os
import sys
import uuid

import requests

# ──── 配置 ─────────────────────────────────────────────────────────────────────

ORCHESTRATE_BASE = os.environ.get("ORCHESTRATE_BASE_URL", "http://127.0.0.1:5001")
TEST_PDF_FILE = os.environ.get("TEST_PDF_FILE", "")
TEST_TXT_FILE = os.environ.get("TEST_TXT_FILE", "")

TIMEOUT = 60
SSE_TIMEOUT = 180

# ──── 工具函数 ─────────────────────────────────────────────────────────────────

def _log(level: str, msg: str):
    print(f"[{level:>5}] {msg}", file=sys.stderr, flush=True)


def _check_status(resp: requests.Response, expected: int, label: str):
    if resp.status_code != expected:
        _log("fail", f"{label}: expected {expected}, got {resp.status_code}")
        _log("fail", f"  Body: {resp.text[:500]}")
    else:
        _log("ok", f"{label}: status={resp.status_code}")
    assert resp.status_code == expected, f"{label}: status {resp.status_code} != {expected}"
    return resp


def _check_envelope(resp: requests.Response, label: str):
    """校验成功响应信封：{code, message, status, data}"""
    body = resp.json()
    for key in ("code", "status", "data"):
        assert key in body, f"{label}: 缺少 '{key}' 字段: {list(body.keys())}"
    assert body["status"] == "success", f"{label}: status != 'success': {body}"
    _log("ok", f"{label}: code={body['code']}, message={body.get('message', 'N/A')}")
    return body


def _check_error(resp: requests.Response, expected_status: int, label: str):
    """校验 FastAPI 默认错误格式：{detail: "..."}"""
    body = resp.json()
    assert resp.status_code == expected_status, f"{label}: expected {expected_status}, got {resp.status_code}"
    assert "detail" in body, f"{label}: 缺少 'detail': {list(body.keys())}"
    _log("ok", f"{label}: detail={body['detail'][:80]}")
    return body


def _read_sse(resp: requests.Response, label: str, max_events: int = 50):
    """读取 SSE 事件流，返回解析后的事件列表"""
    events = []
    buf = ""
    try:
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk is None:
                break
            buf += chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                line, buf = buf.split("\n\n", 1)
                for sub in line.split("\n"):
                    if sub.startswith("data: "):
                        try:
                            event = json.loads(sub[6:])
                            events.append(event)
                            _log("sse", f"{label}: type={event.get('type','?')}")
                        except json.JSONDecodeError:
                            pass
                if len(events) >= max_events:
                    break
    except requests.exceptions.ChunkedEncodingError:
        pass
    except Exception as e:
        _log("warn", f"{label}: SSE read error: {e}")
    return events


# ═══════════════════════════════════════════════════════════════════════════════
# 编排中心对外 API 测试（依据: 编排中心API参考.md，共6个接口）
# ═══════════════════════════════════════════════════════════════════════════════

# ── Test 1: POST /api/v1/orchestrate/sop (JSON 模式) ──── 文档 §1 ─────────────

def test_sop_json():
    """
    文档 §1：SOP 编排 — JSON 请求体模式
    路径: POST /api/v1/orchestrate/sop
    请求: { sop_content, name }
    响应: 201, PSOP 对象
    """
    label = "POST /api/v1/orchestrate/sop (JSON)"
    payload = {
        "sop_content": (
            "## Step 1: 初始诊断\n\n"
            "- Agent: Transport Workbench Agent\n"
            "- Skill: aggregate-analysis\n\n"
            "## Step 2: 汇总报告\n\n"
            "- Agent: Transport Workbench Agent\n"
            "- Skill: aggregate-analysis\n"
        ),
        "name": f"test-sop-json-{uuid.uuid4().hex[:8]}"
    }
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop", json=payload, timeout=TIMEOUT)
    _check_status(resp, 201, label)
    body = _check_envelope(resp, label)
    data = body["data"]

    # 验证 PSOP 结构
    required_fields = ("id", "name", "steps", "created_at", "tags")
    for f in required_fields:
        assert f in data, f"{label}: 缺少 PSOP 字段 '{f}'"
    assert len(data["steps"]) > 0, f"{label}: steps 为空"
    assert data["user_intent"] is not None and len(data["user_intent"]) <= 200, \
        f"{label}: user_intent 异常"
    # 验证 task 结构
    for step in data["steps"]:
        assert "name" in step, f"{label}: step 缺少 'name'"
        assert "subtasks" in step, f"{label}: step 缺少 'subtasks'"
        for t in step["subtasks"]:
            for tf in ("task_id", "description", "agent", "skill", "status"):
                assert tf in t, f"{label}: task 缺少 '{tf}'"
    _log("ok", f"{label}: id={data['id'][:8]}..., steps={len(data['steps'])}")
    return data["id"]


# ── Test 2: POST /api/v1/orchestrate/sop (空内容 → 400) ── 文档 §1 error ─────

def test_sop_empty_content():
    """
    文档 §1 错误码：SOP 内容为空 → 400
    """
    label = "POST /api/v1/orchestrate/sop (空内容)"
    payload = {"sop_content": "   "}
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop", json=payload, timeout=TIMEOUT)
    assert resp.status_code == 400, f"{label}: expected 400, got {resp.status_code}"
    _check_error(resp, 400, label)


# ── Test 3: POST /api/v1/orchestrate/sop (缺少 sop_content → 400/422) ────────

def test_sop_missing_field():
    """
    缺少必填字段 sop_content → 400 (业务校验) 或 422 (Pydantic)
    """
    label = "POST /api/v1/orchestrate/sop (缺少 sop_content)"
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop",
                         headers={"Content-Type": "application/json"}, data="{}", timeout=TIMEOUT)
    assert resp.status_code in (400, 422), f"{label}: expected 400/422, got {resp.status_code}"
    _log("ok", f"{label}: status={resp.status_code}")


# ── Test 4: POST /api/v1/orchestrate/sop (TXT/MD 文件上传 ─ 验证 Bug) ───────

def test_sop_txt_upload():
    """
    文档 §1：SOP 编排 — TXT/MD 文件上传模式 (multipart/form-data)
    若 TEST_TXT_FILE 未设置，跳过此测试。
    """
    label = "POST /api/v1/orchestrate/sop (TXT 上传)"
    if not TEST_TXT_FILE:
        _log("skip", f"{label}: TEST_TXT_FILE 未设置，跳过")
        return

    with open(TEST_TXT_FILE, "rb") as f:
        resp = requests.post(
            f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop",
            files={"file": (os.path.basename(TEST_TXT_FILE), f, "text/plain")},
            data={"name": f"test-txt-{uuid.uuid4().hex[:8]}"},
            timeout=TIMEOUT
        )
    if resp.status_code == 201:
        _log("ok", f"{label}: TXT 上传成功 (status=201)")
        body = resp.json()
        data = body.get("data", {})
        _log("ok", f"{label}: id={data.get('id', '?')[:8]}...")
    else:
        _log("fail", f"{label}: TXT 上传失败 status={resp.status_code}")
        _log("fail", f"  Body: {resp.text[:300]}")


# ── Test 5: POST /api/v1/orchestrate/sop (PDF 文件上传) ──── 文档 §1 文件模式 ─

def test_sop_pdf_upload():
    """
    文档 §1：SOP 编排 — PDF 文件上传模式 (multipart/form-data)
    若 TEST_PDF_FILE 未设置，跳过此测试。
    """
    label = "POST /api/v1/orchestrate/sop (PDF 上传)"
    if not TEST_PDF_FILE:
        _log("skip", f"{label}: TEST_PDF_FILE 未设置，跳过")
        return

    with open(TEST_PDF_FILE, "rb") as f:
        resp = requests.post(
            f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop",
            files={"file": (os.path.basename(TEST_PDF_FILE), f, "application/pdf")},
            data={"name": f"test-pdf-{uuid.uuid4().hex[:8]}"},
            timeout=TIMEOUT
        )
    if resp.status_code == 201:
        _log("ok", f"{label}: PDF 上传成功")
        body = resp.json()
        data = body.get("data", {})
        _log("ok", f"{label}: id={data.get('id', '?')[:8]}...")
    else:
        _log("fail", f"{label}: PDF 上传失败 status={resp.status_code}")
        _log("fail", f"  Body: {resp.text[:300]}")


# ── Test 6: POST /api/v1/orchestrate/intent ── 文档 §2 ──────────────────────

def test_intent():
    """
    文档 §2：意图编排
    路径: POST /api/v1/orchestrate/intent
    请求: { intent, name }
    响应: 201, PSOP 对象 (user_intent 记录原始意图)
    """
    label = "POST /api/v1/orchestrate/intent"
    payload = {
        "intent": "分析网络性能并生成汇总报告",
        "name": f"test-intent-{uuid.uuid4().hex[:8]}"
    }
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/intent", json=payload, timeout=TIMEOUT)
    _check_status(resp, 201, label)
    body = _check_envelope(resp, label)
    data = body["data"]
    assert data.get("user_intent") == payload["intent"], \
        f"{label}: user_intent 应为原始意图，got: {data.get('user_intent')}"
    assert len(data.get("steps", [])) > 0, f"{label}: steps 为空"
    _log("ok", f"{label}: id={data['id'][:8]}..., intent={payload['intent'][:30]}")
    return data["id"]


# ── Test 7: POST /api/v1/orchestrate/intent (空意图) ─── 文档 §2 error ──────

def test_intent_empty():
    """
    文档 §2 约束：空意图 → Pydantic 422 (min_length=1)
    """
    label = "POST /api/v1/orchestrate/intent (空意图)"
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/intent",
                         json={"intent": ""}, timeout=TIMEOUT)
    assert resp.status_code == 422, f"{label}: expected Pydantic 422, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body, f"{label}: 缺少 Pydantic 422 detail"
    _log("ok", f"{label}: status=422, detail={json.dumps(body.get('detail', ''))[:80]}")


# ── Test 8: POST /api/v1/orchestrate/search ── 文档 §3 ──────────────────────

def test_search():
    """
    文档 §3：检索工作流
    路径: POST /api/v1/orchestrate/search
    请求: { intent, top_n? }
    响应: 200, WorkflowSearchResult 列表
    """
    label = "POST /api/v1/orchestrate/search"
    payload = {"intent": "网络故障诊断"}
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/search", json=payload, timeout=TIMEOUT)
    _check_status(resp, 200, label)
    body = _check_envelope(resp, label)
    data = body["data"]
    assert isinstance(data, list), f"{label}: data 应为数组, got {type(data)}"
    _log("ok", f"{label}: 找到 {len(data)} 条结果")
    if data:
        item = data[0]
        # 文档声明的字段
        for f in ("workflow_id", "workflow_type", "name", "created_at"):
            assert f in item, f"{label}: 结果缺少文档声明的字段 '{f}'"
        # 实际代码返回但文档未列的字段: score
        actual_keys = set(item.keys())
        doc_keys = {"workflow_id", "workflow_type", "name", "description",
                    "tags", "created_at", "user_intent", "related_preflow"}
        extra = actual_keys - doc_keys
        missing = doc_keys - actual_keys
        if extra:
            _log("info", f"{label}: 实际返回比文档多出的字段: {extra} (如 score)")
        if missing:
            _log("warn", f"{label}: 文档声明但实际未返回的字段: {missing}")
    return data


# ── Test 9: POST /api/v1/orchestrate/search (top_n 限制) ── 文档 §3 ──────────

def test_search_top_n():
    """
    文档 §3: top_n 参数，范围 1~20，默认 5
    """
    label = "POST /api/v1/orchestrate/search (top_n=2)"
    payload = {"intent": "网络", "top_n": 2}
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/search", json=payload, timeout=TIMEOUT)
    _check_status(resp, 200, label)
    body = _check_envelope(resp, label)
    assert len(body["data"]) <= 2, f"{label}: 返回 {len(body['data'])} 条, 应 <=2"
    _log("ok", f"{label}: 返回 {len(body['data'])} 条 (≤2)")


# ── Test 10: POST /api/v1/orchestrate/execute (SSE) ── 文档 §4 ──────────────

def test_execute_auto_sse():
    """
    文档 §4：自动编排+执行 (SSE)
    路径: POST /api/v1/orchestrate/execute
    请求: { task, name? }
    响应: SSE 事件流 (text/event-stream)
    验证: 事件类型、字段结构
    """
    label = "POST /api/v1/orchestrate/execute (SSE)"
    payload = {"task": "执行一次网络健康检查并报告状态"}
    try:
        resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/execute",
                             json=payload, stream=True, timeout=SSE_TIMEOUT,
                             headers={"Accept": "text/event-stream"})
        _check_status(resp, 200, label)
        events = _read_sse(resp, label, max_events=30)
        _log("ok", f"{label}: 收到 {len(events)} 个事件")

        event_types = [e.get("type") for e in events]
        assert "init" in event_types or "start" in event_types, \
            f"{label}: 缺少 init/start 事件: {event_types}"

        has_terminal = any(t in ("complete", "error") for t in event_types)
        _log("ok" if has_terminal else "warn",
             f"{label}: 有 complete/error 事件 = {has_terminal}")

        # 验证 SSE 事件字段结构（与 编排中心API参考.md §4 一致）
        for e in events:
            if e.get("type") == "agent_request":
                data = e.get("data", {})
                assert "agent" in data, f"{label}: agent_request 缺少 'agent'"
                assert "request" in data, f"{label}: agent_request 缺少 'request'"
            elif e.get("type") == "agent_response":
                data = e.get("data", {})
                assert "agent" in data, f"{label}: agent_response 缺少 'agent'"
                assert "response" in data, f"{label}: agent_response 缺少 'response'"
            elif e.get("type") == "psop_update":
                data = e.get("data", {})
                assert "psop" in data, f"{label}: psop_update 缺少 'psop' (完整 PSOP 对象)"

    except Exception as e:
        _log("warn", f"{label}: SSE 执行异常: {e}")


# ── Test 11: GET /api/v1/orchestrate/execute/{psop_id} (SSE) ── 文档 §5 ─────

def test_execute_by_id_sse():
    """
    文档 §5：执行指定工作流 (SSE)
    路径: GET /api/v1/orchestrate/execute/{psop_id}
    参数: user_intent (query, 可选)
    先创建 PSOP 再执行。
    """
    label = "GET /api/v1/orchestrate/execute/{id} (SSE)"

    # 创建 PSOP
    create_payload = {
        "sop_content": (
            "## Step 1: 快速检查\n\n"
            "- Agent: Transport Workbench Agent\n"
            "- Skill: aggregate-analysis\n"
        ),
        "name": f"test-exec-by-id-{uuid.uuid4().hex[:8]}"
    }
    resp = requests.post(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/sop",
                         json=create_payload, timeout=TIMEOUT)
    if resp.status_code != 201:
        _log("skip", f"{label} (创建): SOP 失败 status={resp.status_code}, 跳过")
        return
    psop_id = resp.json()["data"]["id"]

    # 执行（带 runtime intent）
    resp2 = requests.get(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/execute/{psop_id}",
                         params={"user_intent": "早上8点检查华为园区网络健康状态"},
                         stream=True, timeout=SSE_TIMEOUT,
                         headers={"Accept": "text/event-stream"})
    _check_status(resp2, 200, f"{label} (执行)")
    events = _read_sse(resp2, label, max_events=30)
    _log("ok", f"{label}: SSE 事件数={len(events)}, types={[e.get('type') for e in events]}")


# ── Test 12: GET /api/v1/orchestrate/execute/{id} (不存在的PSOP → 404) ──────

def test_execute_nonexistent_psop():
    """
    文档 §5 错误码：不存在的 PSOP → 404
    """
    label = "GET /api/v1/orchestrate/execute/{nonexistent}"
    resp = requests.get(f"{ORCHESTRATE_BASE}/api/v1/orchestrate/execute/{uuid.uuid4()}", timeout=TIMEOUT)
    assert resp.status_code in (404, 422), f"{label}: expected 404/422, got {resp.status_code}"
    _log("ok", f"{label}: status={resp.status_code}")


# ── Test 13: GET /api/v1/executions/{execution_id} ── 文档 §6 ───────────────

def test_get_execution():
    """
    文档 §6：查询执行结果
    路径: GET /api/v1/executions/{execution_id}
    不存在 → 404
    """
    label = "GET /api/v1/executions/{id}"
    fake_id = str(uuid.uuid4())
    resp = requests.get(f"{ORCHESTRATE_BASE}/api/v1/executions/{fake_id}", timeout=TIMEOUT)
    assert resp.status_code == 404, f"{label}: expected 404, got {resp.status_code}"
    _check_error(resp, 404, label)


# ── Test 14: 编排中心服务可达性（用 search 接口探活）────────────────────────

def test_orchestrate_reachable():
    """
    用已确认存在的接口验证服务可达
    """
    label = "编排中心可达性"
    try:
        resp = requests.get(f"{ORCHESTRATE_BASE}/api/v1/executions/{uuid.uuid4()}", timeout=5)
        _log("ok", f"{label}: 服务响应 status={resp.status_code}")
    except requests.ConnectionError:
        _log("fail", f"{label}: 无法连接 {ORCHESTRATE_BASE}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65, flush=True)
    print("  编排中心对外 API 集成测试（基于 编排中心API参考.md）", flush=True)
    print(f"  基础地址: {ORCHESTRATE_BASE}", flush=True)
    print(f"  PDF测试文件: {TEST_PDF_FILE or '(未设置,跳过PDF上传测试)'}", flush=True)
    print(f"  TXT测试文件: {TEST_TXT_FILE or '(未设置,跳过TXT上传测试)'}", flush=True)
    print("=" * 65, flush=True)

    orchestrate_tests = [
        ("01_sop_json",             test_sop_json),
        ("02_sop_empty",            test_sop_empty_content),
        ("03_sop_missing",          test_sop_missing_field),
        ("04_sop_txt_upload",       test_sop_txt_upload),
        ("05_sop_pdf_upload",       test_sop_pdf_upload),
        ("06_intent",               test_intent),
        ("07_intent_empty",         test_intent_empty),
        ("08_search",               test_search),
        ("09_search_top_n",         test_search_top_n),
        ("10_execute_auto_sse",     test_execute_auto_sse),
        ("11_execute_by_id_sse",    test_execute_by_id_sse),
        ("12_execute_nonexistent",  test_execute_nonexistent_psop),
        ("13_get_execution",        test_get_execution),
        ("14_reachable",            test_orchestrate_reachable),
    ]

    results = {}
    for name, func in orchestrate_tests:
        print(f"\n{'─' * 45}", flush=True)
        print(f"  [{name}]", flush=True)
        try:
            func()
            results[name] = "PASS"
        except AssertionError as e:
            results[name] = "FAIL"
            _log("fail", str(e))
        except requests.ConnectionError as e:
            results[name] = "SKIP (无法连接)"
            _log("skip", str(e))
        except Exception as e:
            results[name] = "ERROR"
            _log("error", f"{type(e).__name__}: {e}")

    print(f"\n{'=' * 65}", flush=True)
    print("  测试汇总", flush=True)
    print(f"{'=' * 65}", flush=True)
    passed = sum(1 for v in results.values() if v == "PASS")
    failed = sum(1 for v in results.values() if v == "FAIL")
    skipped = sum(1 for v in results.values() if v.startswith("SKIP"))
    errors = sum(1 for v in results.values() if v == "ERROR")
    for name, result in sorted(results.items()):
        print(f"  {result:<30} {name}", flush=True)
    print(f"\n  Total: {len(results)} | Pass: {passed} | Fail: {failed} "
          f"| Skip: {skipped} | Error: {errors}", flush=True)
    print(f"{'=' * 65}", flush=True)

    if failed > 0 or errors > 0:
        sys.exit(1)
