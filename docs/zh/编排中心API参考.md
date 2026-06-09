# 编排中心API参考

## 使用前必读

### 简介

  编排中心是一个面向多智能体（Agent）协作的可视化编排平台，对外提供以下 RESTful API 接口，供其他系统集成调用：

  - **SOP 编排**：上传 PDF/TXT/MD 文件或提交自然语言 SOP 步骤，自动生成 PSOP 工作流。
  - **意图编排**：提交自然语言任务意图，由 LLM 自主规划生成 PSOP 工作流。
  - **检索工作流**：提交自然语言意图，匹配平台内已有工作流，返回最相关的 TopN 个工作流（含 ID、名称、描述等）。
  - **自动编排+执行**：提交任务描述，自动检索匹配工作流并执行；无匹配则自动生成工作流后执行，通过 SSE 实时推送进度与结果。
  - **执行指定工作流**：根据已知的 PSOP ID 启动执行，通过 SSE 实时推送执行进度与结果。
  - **查询执行结果**：根据执行 ID 获取工作流执行记录的详细信息。

  所有接口基础路径为 **`/api/v1`**。

### 响应格式

  所有接口（除 SSE 流式接口外）统一返回以下 JSON 结构：

  | 参数名称  | 类型     | 描述                                      |
  |-----------|----------|-------------------------------------------|
  | code      | integer  | HTTP 状态码，200 表示成功，201 表示创建成功 |
  | message   | string   | 响应消息描述                              |
  | status    | string   | 响应状态，成功为 `"success"`              |
  | data      | object   | 响应数据，具体结构参见各接口              |

  错误响应统一格式（与成功响应一致）：

  | 参数名称 | 类型    | 描述                                        |
  |----------|---------|---------------------------------------------|
  | code     | integer | HTTP 状态码（如 400、404、422、500）        |
  | message  | string  | 错误描述信息                                 |
  | status   | string  | `"error"`                                    |
  | data     | object  | `null`                                       |

### 约束与限制

  - 各接口均受并发控制（Semaphore）与令牌桶限流（RateLimiter）双重保护，详见各接口约束。
  - 服务端口默认为 **5001**。

---

## 1. SOP 编排接口

- 典型场景

    用户持有解决方案包文档（PDF/TXT/MD 格式），或直接输入自然语言 SOP 步骤描述，需要自动生成多 Agent 协作的 PSOP 工作流。

- 功能描述

    接收 PDF/TXT/MD 文件（PDF 解析 "5. Interaction Flow" 章节，TXT/MD 直接读取全文）或 JSON 格式的 SOP 步骤文本，结合可用 Agent 列表，由 LLM 生成 PSOP 工作流并自动保存。

- 接口约束

  - 文件上传模式：仅支持 PDF、TXT、MD 格式，文件名须匹配 `^[\w\-. ]{1,128}\.(pdf|txt|md)$`。
  - 单文件不超过 100 MB。
  - PDF 文件须以 `%PDF-` 开头（magic bytes 校验）。
  - 限流标识：`sop_orchestrate`，速率由 `FLOW_CTL_PLAN` 配置决定。
  - 单实例上该接口最大并发数由 `server.conf` 中 `FLOW_CTL_PLAN` 配置决定。

- 调用方法

    POST

- URI

    `/api/v1/orchestrate/sop`

- 请求参数

    **模式 A：文件上传（multipart/form-data）**

    | 参数名称 | 是否必选 | 类型   | 值域            | 默认值 | 描述                        |
    |----------|----------|--------|-----------------|--------|-----------------------------|
    | file     | 否       | file   | PDF/TXT/MD 文件  | -      | 待解析的解决方案包文件       |
    | name     | 否       | string | -               | -      | 可选的工作流名称            |

    **模式 B：JSON 请求体（application/json）**

    | 参数名称    | 是否必选 | 类型   | 值域 | 默认值 | 描述                      |
    |-------------|----------|--------|------|--------|---------------------------|
    | sop_content | 是       | string | -    | -      | 自然语言 SOP 步骤（Markdown） |
    | name        | 否       | string | -    | -      | 可选的工作流名称           |

    > **优先级**：若同时提供文件与 JSON 请求体，文件优先。

- 请求示例

    **文件上传：**

    ```
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

    ------WebKitFormBoundary
    Content-Disposition: form-data; name="file"; filename="solution.pdf"
    Content-Type: application/pdf

    [PDF文件二进制数据]
    ------WebKitFormBoundary
    Content-Disposition: form-data; name="name"

    我的工作流
    ------WebKitFormBoundary--
    ```

    **JSON 请求体：**

    ```json
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

    {
        "sop_content": "## 节能流程\n1. 收集设备状态数据\n2. 分析能耗基线\n3. 执行节能策略",
        "name": "节能评估"
    }
    ```

- 响应参数

    | 参数名称 | 类型   | 描述                           |
    |----------|--------|--------------------------------|
    | code     | integer | 201 表示创建成功               |
    | message  | string | 固定返回 `"PSOP generated and saved"` |
    | status   | string | `"success"`                    |
    | data     | object | 生成的 PSOP 工作流完整对象      |

    **PSOP 对象结构（data 字段）**: 参见 [附录 A：PSOP 数据结构](#附录-apsop-数据结构)。

- 响应示例

    ```json
    {
        "code": 201,
        "message": "PSOP generated and saved",
        "status": "success",
        "data": {
            "id": "a1b2c3d4-...",
            "name": "节能评估",
            "description": "基于SOP生成的节能工作流",
            "created_at": "2026-05-22T10:30:00.123456",
            "steps": [ ... ],
            "related_preflow": "preflow-uuid-...",
            "user_intent": "用户原始SOP步骤文本前200字符",
            "tags": []
        }
    }
    ```

- 错误码

    | 状态码 | 说明                               |
    |--------|------------------------------------|
    | 400    | 文件名不合法、PDF 格式无效、SOP 内容为空、解析章节失败 |
    | 413    | 文件超过 100 MB                     |
    | 422    | `sop_content` 字段缺失（Pydantic 校验） |
    | 500    | PDF 解析发生内部错误                 |
    | 503    | 并发数已满，服务器繁忙              |

---

## 2. 意图编排接口

- 典型场景

    用户仅有高层次的业务意图描述（如"帮我做一次全网节能优化"），无需提供具体步骤，由 LLM 自主规划生成工作流。

- 功能描述

    接收自然语言任务意图，结合可用 Agent 列表，由 LLM 自主规划并生成 PSOP 工作流，自动保存。

- 接口约束

  - 限流标识：`intent_orchestrate`，速率由 `FLOW_CTL_GENERATE_PSOP` 配置决定。
  - 单实例上该接口最大并发数由 `server.conf` 中 `FLOW_CTL_GENERATE_PSOP` 配置决定。

- 调用方法

    POST

- URI

    `/api/v1/orchestrate/intent`

- 请求参数

    JSON 请求体（application/json）：

    | 参数名称 | 是否必选 | 类型   | 值域 | 默认值 | 描述                       |
    |----------|----------|--------|------|--------|----------------------------|
    | intent   | 是       | string | -    | -      | 自然语言任务意图描述        |
    | name     | 否       | string | -    | -      | 可选的工作流名称            |

- 请求示例

    ```json
    POST /api/v1/orchestrate/intent HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

    {
        "intent": "帮我做一次全网节能优化",
        "name": "全网节能优化"
    }
    ```

- 响应参数

    | 参数名称 | 类型   | 描述                           |
    |----------|--------|--------------------------------|
    | code     | integer | 201 表示创建成功               |
    | message  | string | 固定返回 `"PSOP generated and saved"` |
    | status   | string | `"success"`                    |
    | data     | object | 生成的 PSOP 工作流完整对象      |

- 响应示例

    ```json
    {
        "code": 201,
        "message": "PSOP generated and saved",
        "status": "success",
        "data": {
            "id": "e5f6g7h8-...",
            "name": "全网节能优化",
            "description": null,
            "created_at": "2026-05-22T10:31:00.123456",
            "steps": [ ... ],
            "tags": ["节能", "全网"]
        }
    }
    ```

- 错误码

    | 状态码 | 说明                  |
    |--------|-----------------------|
    | 404    | 无可用 Agent          |
    | 422    | `intent` 字段为空或缺失（Pydantic 校验，min_length=1） |
    | 503    | 并发数已满，服务器繁忙 |

---

## 3. 检索工作流接口

- 典型场景

    用户已知任务意图，需要先从平台中查找是否存在匹配的已有 PSOP 工作流，再决定是直接执行还是新生成一个。适用于"先查后用"的调用模式。

- 功能描述

    接收自然语言意图，通过 LLM 语义匹配平台内已保存的 PSOP 工作流，返回最相关的 TopN 个结果摘要（包含工作流 ID、名称、描述、标签等），供调用方选择或进一步操作。

- 接口约束

  - 限流标识：`retrieve_by_intent`，速率由 `FLOW_CTL_RETRIEVE_PSOP` 配置决定。

- 调用方法

    POST

- URI

    `/api/v1/orchestrate/search`

- 请求参数

    JSON 请求体（application/json）：

    | 参数名称 | 是否必选 | 类型    | 值域        | 默认值 | 描述                                         |
    |----------|----------|---------|-------------|--------|----------------------------------------------|
    | intent   | 是       | string  | -           | -      | 自然语言意图描述，用于语义匹配已有工作流      |
    | top_n    | 否       | integer | 1 ~ 20      | 5      | 最大返回结果数，按相关度降序排列              |

- 请求示例

    ```json
    POST /api/v1/orchestrate/search HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

    {
        "intent": "帮我做一次网络故障根因分析",
        "top_n": 3
    }
    ```

- 响应参数

    | 参数名称 | 类型   | 描述                                     |
    |----------|--------|------------------------------------------|
    | code     | integer | 200 表示成功                             |
    | message  | string | 如 `"Found 3 matching workflow(s)"`      |
    | status   | string | `"success"`                              |
    | data     | array  | 匹配的工作流摘要列表，按相关度降序排列     |

    **data 数组每个元素（WorkflowSearchResult）结构：**

    | 参数名称         | 类型             | 描述                                          |
    |------------------|------------------|-----------------------------------------------|
    | workflow_id      | string (UUID)    | 工作流唯一标识，可用于后续执行接口             |
    | workflow_type    | string           | 工作流类型，固定为 `"psop"`                    |
    | name             | string           | 工作流名称                                    |
    | description      | string \| null   | 工作流简要描述                                |
    | tags             | array[string]    | 标签列表                                      |
    | created_at       | string (ISO8601) | 创建时间戳                                    |
    | score            | float            | 相关度评分（0~1），值越大表示匹配度越高        |
    | user_intent      | string \| null   | 生成该工作流时的原始用户意图                  |
    | related_preflow  | string \| null   | 关联的 PreFlow ID                             |

- 响应示例

    ```json
    {
        "code": 200,
        "message": "Found 3 matching workflow(s)",
        "status": "success",
        "data": [
            {
                "workflow_id": "a1b2c3d4-...",
                "workflow_type": "psop",
                "name": "网络故障根因分析",
                "description": "自动化网络故障定位与根因分析工作流",
                "tags": ["网络", "故障", "诊断"],
                "created_at": "2026-05-20T09:15:00.000000",
                "user_intent": "帮我分析网络中断原因",
                "related_preflow": null
            },
            {
                "workflow_id": "e5f6g7h8-...",
                "workflow_type": "psop",
                "name": "SPN故障处理",
                "description": "SPN设备故障检测与恢复流程",
                "tags": ["SPN", "故障", "恢复"],
                "created_at": "2026-05-18T14:30:00.000000",
                "user_intent": "SPN故障定位和处理",
                "related_preflow": null
            }
        ]
    }
    ```

- 错误码

    | 状态码 | 说明                  |
    |--------|-----------------------|
    | 500    | LLM 检索调用失败      |

---

## 3.5 获取工作流详情

- 典型场景

  通过检索接口获取工作流 ID 后，获取该工作流的完整详情。

- 功能描述

  根据 PSOP ID 获取完整工作流定义。返回所有步骤（step）、任务（subtask）、跳转条件（next condition）等细节。

- 接口约束

  - 限流标识：`get_workflow`，速率由 `FLOW_CTL_ONE_PSOP` 配置决定。

- 调用方法

  GET

- URI

  `/api/v1/orchestrate/psop/{psop_id}`

- 请求参数

  | 参数名  | 类型   | 必填 | 位置 | 描述                |
  |--------|--------|------|------|---------------------|
  | psop_id | string | 是   | path | PSOP 工作流唯一标识  |

- 请求示例

  ```
  GET /api/v1/orchestrate/psop/06cb53d9-de27-4adf-9898-2eae5afcf888
  ```

- 返回参数（data 字段）

  详见 [PSOP 数据结构](#附录-a-psop-数据结构)。

- 错误码

  | 状态码 | 说明                  |
  |--------|-----------------------|
  | 404    | 指定 ID 的工作流不存在 |
  | 500    | 服务器内部错误         |

---

## SSE 事件类型说明

以下执行接口（`POST /orchestrate/execute`、`GET /orchestrate/execute/{psop_id}`）通过 SSE（Server-Sent Events）实时推送执行进度。每条 SSE 消息格式为：

```
data: {"type": "<事件类型>", "data": {<事件数据>}, "timestamp": <时间戳>}
```

### 事件类型一览

| 事件类型         | 说明 | 触发时机 | data 字段关键内容 |
|-----------------|------|----------|-------------------|
| `init`          | 引擎初始化完成 | 执行开始时 | `psop_id` — 工作流 ID |
| `start`         | 流程开始执行 | init 之后 | `psop_id`, `message` |
| `agent_request` | 向 Agent 发送任务 | 每步开始时 | `agent` — 目标 agent 名, `request` — protobuf 格式的请求体 |
| `agent_response`| Agent 返回结果 | 每步完成时 | `agent` — 来源 agent 名, `response` — protobuf 格式的响应体 |
| `psop_update`   | 工作流状态更新 | 每步完成后 | `psop` — 完整 PSOP JSON（含各任务 status: pending/success/failed） |
| `complete`      | 工作流执行完成 | 所有步骤完成后 | `psop_id`, `execution_history` — 步骤级执行历史 |
| `error`         | 执行异常 | 执行失败或取消时 | `psop_id`, `error` — 错误描述 |
| `close`         | SSE 连接关闭 | complete/error 之后 | 空 `{}` |

### SSE 事件推送示例

**正常流程序列：**
```
init → start → agent_request → agent_response → psop_update
  → agent_request → agent_response → psop_update
  → ... (每步重复) ...
  → complete → close
```

**错误中断序列：**
```
init → start → ... → error → close
```

### 解析示例（Python）

```python
import requests, json
resp = requests.get(
    "http://127.0.0.1:5001/api/v1/orchestrate/execute/{psop_id}?lang=zh",
    stream=True,
)
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    event = json.loads(line[6:])
    etype = event["type"]
    if etype == "agent_request":
        print(f"→ {event['data']['agent']}")
    elif etype == "agent_response":
        print(f"← {event['data']['agent']}")
    elif etype == "psop_update":
        psop = event["data"].get("psop", {})
        if isinstance(psop, str):
            psop = json.loads(psop)
        for step in psop.get("steps", []):
            print(f"  {step['name']}: {[t['status'] for t in step['subtasks']]}")
    elif etype in ("complete", "error"):
        print(f"[{etype}]")
        break
```

---

## 4. 自动编排+执行接口

- 典型场景

    用户直接提交任务需求，系统自动判定是否有匹配的已有工作流，有则直接执行，无则先生成再执行。适用于"一句话驱动"的端到端任务场景。

- 功能描述

    接收任务描述文本，首先通过 LLM 检索匹配的已有 PSOP 工作流。若匹配成功，直接以 SSE 流执行；若无匹配，自动调用意图编排生成新的 PSOP，保存后立即执行。全程通过 SSE（Server-Sent Events）实时推送执行进度。

- 接口约束

  - 限流标识：`ext_execute_auto`，速率由 `FLOW_CTL_START_PROCESS_STREAM` 配置决定。
  - 单实例上该接口最大并发数由 `server.conf` 中 `FLOW_CTL_START_PROCESS_STREAM` 配置决定。
  - 响应为 SSE 流式连接，请确保客户端支持 `text/event-stream` 类型的长连接。

- 调用方法

    POST

- URI

    `/api/v1/orchestrate/execute`

- 请求参数

    JSON 请求体（application/json）：

    | 参数名称 | 是否必选 | 类型   | 值域 | 默认值 | 描述                                   |
    |----------|----------|--------|------|--------|----------------------------------------|
    | task     | 是       | string | -    | -      | 任务描述，系统会先检索已有 PSOP，无匹配则自动生成 |
    | name     | 否       | string | -    | -      | 可选的工作流名称（用于自动生成场景）     |

- 请求示例

    ```json
    POST /api/v1/orchestrate/execute HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

    {
        "task": "帮我做一次网络故障根因分析",
        "name": "故障根因分析"
    }
    ```

- 响应格式（SSE 事件流）

    响应为 `text/event-stream`，事件格式如下：

    ```
    data: {"type": "init", "data": {...}}
    data: {"type": "start", "data": {...}}
    data: {"type": "agent_request", "data": {...}}
    data: {"type": "agent_response", "data": {...}}
    data: {"type": "psop_update", "data": {...}}
    data: {"type": "complete", "data": {...}}
    event: close
    data: {}
    ```

    **SSE 事件类型说明：**

    | 事件类型       | 描述                                                    |
    |----------------|---------------------------------------------------------|
    | init           | 执行引擎初始化，包含 `psop_id`                           |
    | start          | 执行开始通知                                            |
    | agent_request  | Agent 任务下发事件，包含 `agent`（Agent名称）、`request`（下发请求内容） |
    | agent_response | Agent 执行结果返回事件，包含 `agent`（Agent名称）、`response`（执行结果内容） |
    | psop_update    | PSOP 工作流状态更新，包含 `psop`（完整 PSOP 对象，含各子任务最新状态） |
    | complete       | 所有步骤执行完成，包含 `execution_history` 汇总           |
    | error          | 执行失败，包含 `error` 描述                              |
    | close          | SSE 流结束信号                                          |

    每个事件 JSON 包含 `type`（事件类型）、`data`（事件数据）、`timestamp`（时间戳）三个字段。

    执行完成后，系统自动保存 `ExecutionRecord` 执行记录，可通过 [查询执行结果详情](#7-查询执行结果详情) 获取详情。

- 响应示例

    ```
    data: {"type":"init","data":{"psop_id":"a1b2c3d4-...","message":"Initializing execution engine"},"timestamp":12345.67}
    data: {"type":"start","data":{"psop_id":"a1b2c3d4-...","message":"Execution started"},"timestamp":12345.68}
    data: {"type":"agent_request","data":{"agent":"RAN Energy Saver","request":"{\"message\":...}"},"timestamp":12345.70}
    data: {"type":"agent_response","data":{"agent":"RAN Energy Saver","response":"{\"status\":{\"state\":\"TASK_STATE_COMPLETED\"},...}"},"timestamp":12346.50}
    data: {"type":"psop_update","data":{"psop":{"id":"...","steps":[...]}},"timestamp":12346.51}
    data: {"type":"complete","data":{"psop_id":"a1b2c3d4-...","execution_history":[...]},"timestamp":12347.00}
    event: close
    data: {}
    ```

- 错误码

    | 状态码 | 说明                              |
    |--------|-----------------------------------|
    | 500    | 自动生成 PSOP 失败                 |
    | 503    | 并发数已满，服务器繁忙             |

    > 执行过程中的运行时错误通过 SSE `error` 事件推送，不会体现在 HTTP 状态码上。

---

## 5. 执行指定工作流接口

- 典型场景

    调用方先通过 [检索工作流接口](#3-检索工作流接口) 查到了目标工作流 ID，或从其他渠道已知 PSOP ID，希望直接启动执行。典型流程为：检索工作流 → 选择目标 → 执行指定工作流。

- 功能描述

    根据 PSOP ID 查找工作流，以 SSE 流方式启动执行，实时推送执行进度与结果。

- 接口约束

  - 限流标识：`ext_execute_by_id`，速率由 `FLOW_CTL_START_PROCESS_STREAM` 配置决定。
  - 单实例上该接口最大并发数由 `server.conf` 中 `FLOW_CTL_START_PROCESS_STREAM` 配置决定。
  - 响应为 SSE 流式连接。

- 调用方法

    GET

- URI

    `/api/v1/orchestrate/execute/{psop_id}`

- 请求参数

    | 参数名称     | 是否必选 | 类型   | 位置   | 默认值 | 描述                                           |
    |--------------|----------|--------|--------|--------|------------------------------------------------|
    | psop_id      | 是       | string | path   | -      | PSOP 工作流 ID                                  |
    | user_intent  | 否       | string | query  | -      | 运行时用户意图，用于 Agent 上下文注入，执行时传入 |

- 请求示例

    ```
    GET /api/v1/orchestrate/execute/a1b2c3d4-e5f6-7890-abcd-ef1234567890?user_intent=帮我查基站节能率 HTTP/1.1
    Host: your-host:5001
    ```

- 响应格式（SSE 事件流）

    与 [自动编排+执行接口](#4-自动编排执行接口) 相同的 SSE 事件格式。

- 错误码

    | 状态码 | 说明                  |
    |--------|-----------------------|
    | 404    | 指定 PSOP 不存在      |
    | 503    | 并发数已满，服务器繁忙 |

---

## 6. 查询执行记录列表

- 典型场景

  获取历史执行记录的摘要列表，用于监控或排查历史执行情况。

- 功能描述

  返回按时间倒序排列的执行记录摘要，每条包含执行 ID、关联的 PSOP 信息、状态和时间戳。不包含完整的 events 和 execution_history 细节。

- 接口约束

  - 限流标识：`list_executions`，速率由 `FLOW_CTL_ALL_PSOPS` 配置决定。

- 调用方法

  GET

- URI

  `/api/v1/executions`

- 请求参数

  无。

- 请求示例

  ```
  GET /api/v1/executions
  ```

- 返回参数（data 字段）

  | 参数名        | 类型      | 描述                           |
  |--------------|-----------|--------------------------------|
  |              | array     | 执行记录摘要列表               |
  | execution_id | string    | 执行记录唯一标识               |
  | psop_id      | string    | 关联的 PSOP ID                 |
  | psop_name    | string    | 关联的 PSOP 名称               |
  | started_at   | string    | 开始时间（ISO 8601）           |
  | completed_at | string    | 完成时间（ISO 8601）           |
  | status       | string    | 执行状态: success, failed, stopped |
  | step_count   | integer   | 执行的步骤数                   |
  | error        | string    | 错误信息（如有）               |

- 返回示例

  ```json
  {
      "code": 200,
      "message": "Found 2 execution record(s)",
      "status": "success",
      "data": [
          {
              "execution_id": "7273ca6b-e75f-4a69-a645-b8bb59a3e622",
              "psop_id": "8598d5ee-56bc-4fd9-a039-865ec0137cc8",
              "psop_name": "基站节能闭环",
              "started_at": "2026-06-02T07:01:03.994Z",
              "completed_at": "2026-06-02T07:01:25.492Z",
              "status": "success",
              "step_count": 4,
              "error": null
          }
      ]
  }
  ```

---

## 7. 查询执行结果详情

- 典型场景

    工作流执行完成后（或执行中断后），调用方需要查询某次执行的完整记录，包括步骤级执行历史、Agent 交互事件、最终状态等。

- 功能描述

    根据执行 ID 获取执行记录详情，包含执行状态、步骤历史、Agent 交互事件、完成时间、错误信息（如有）等。

- 接口约束

  - 限流标识：`get_execution`，速率由 `FLOW_CTL_ONE_PSOP`（内部映射） 配置决定。

- 调用方法

    GET

- URI

    `/api/v1/executions/{execution_id}`

- 请求参数

    | 参数名称      | 是否必选 | 类型   | 位置 | 默认值 | 描述           |
    |---------------|----------|--------|------|--------|----------------|
    | execution_id  | 是       | string | path | -      | 执行记录 ID     |

- 请求示例

    ```
    GET /api/v1/executions/exec-uuid-12345678 HTTP/1.1
    Host: your-host:5001
    ```

- 响应参数

    | 参数名称 | 类型   | 描述                                          |
    |----------|--------|-----------------------------------------------|
    | code     | integer | 200 表示成功                                  |
    | message  | string | 固定返回 `"success"`                          |
    | status   | string | `"success"`                                   |
    | data     | object | ExecutionRecord 执行记录对象                   |

    **ExecutionRecord 对象结构（data 字段）**：参见 [附录 B：ExecutionRecord 数据结构](#附录-bexecutionrecord-数据结构)。

- 响应示例

    ```json
    {
        "code": 200,
        "message": "success",
        "status": "success",
        "data": {
            "execution_id": "exec-uuid-12345678",
            "psop_id": "a1b2c3d4-...",
            "psop_name": "节能评估",
            "started_at": "2026-05-22T10:30:00.000000",
            "completed_at": "2026-05-22T10:31:30.000000",
            "status": "success",
            "execution_history": [ ... ],
            "final_psop": { ... },
            "events": [ ... ],
            "error": null
        }
    }
    ```

- 错误码

    | 状态码 | 说明                      |
    |--------|---------------------------|
    | 404    | 指定执行记录不存在         |

---

## 附录

### 附录 A：PSOP 数据结构

| 字段名          | 类型             | 描述                                                        |
|-----------------|------------------|-------------------------------------------------------------|
| id              | string (UUID)    | 工作流唯一标识                                                |
| name            | string           | 工作流名称                                                    |
| description     | string \| null   | 工作流简要描述                                                |
| created_at      | string (ISO8601) | 创建时间戳                                                    |
| steps           | array[Step]      | 工作流步骤列表（见下方 Step 结构）                             |
| related_preflow | string \| null   | 关联的 PreFlow ID（由 SOP 编排生成时填充）                     |
| user_intent     | string \| null   | 生成该工作流的原始用户意图                                    |
| tags            | array[string]    | 标签列表，用于分类和检索                                      |

**Step 结构：**

| 字段名      | 类型                   | 描述                                                              |
|-------------|------------------------|-------------------------------------------------------------------|
| name        | string                 | 步骤标识（如 `"step1"`）                                          |
| type        | string                 | 步骤成功条件：`"AllSuccess"`（全部子任务成功）或 `"AnySuccess"`（任一子任务成功） |
| subtasks    | array[Task]            | 子任务列表，子任务间无依赖，可并行执行                            |
| next        | array[JumpCondition] \| null | 跳转条件列表，指向下一步骤；空值表示无条件顺序执行              |
| layer       | integer                | 编排层级：0 = 执行层（叶子 Agent），1+ = 聚合层                  |
| context_from | array[string] \| null  | 上下文来源步骤列表，`["*"]` 表示包含所有直接前驱（有边流入本节点的步骤）的输出；为 null 且 layer > 0 时自动从图拓扑推导 |

**Task 结构：**

| 字段名      | 类型   | 描述                               |
|-------------|--------|------------------------------------|
| task_id     | string | 唯一任务标识 (UUID)                |
| description | string | 任务描述                           |
| agent       | string | 执行该任务的 Agent 名称            |
| skill       | string | 执行该任务所需的技能名称           |
| status      | string | 任务状态：`"pending"` / `"running"` / `"success"` / `"failed"` |

**JumpCondition 结构：**

| 字段名    | 类型   | 描述                 |
|-----------|--------|----------------------|
| step      | string | 目标步骤名称         |
| condition | string | 跳转条件描述         |

---

### 附录 B：ExecutionRecord 数据结构

| 字段名            | 类型             | 描述                                                    |
|-------------------|------------------|---------------------------------------------------------|
| execution_id      | string (UUID)    | 执行记录唯一标识                                          |
| psop_id           | string           | 执行的 PSOP 工作流 ID                                    |
| psop_name         | string           | 执行的 PSOP 工作流名称                                    |
| started_at        | string (ISO8601) | 执行开始时间                                              |
| completed_at      | string \| null   | 执行完成时间（失败时仍会记录）                            |
| status            | string           | 执行状态：`"running"` / `"success"` / `"failed"` / `"stopped"` |
    | execution_history | array[object]    | 步骤级执行历史，每项包含 `step`（步骤名）、`task`（任务描述）、`status`（"success" / "failed"）、`output`（执行输出） |
| final_psop        | object \| null   | 执行完成时带任务状态的最终 PSOP 快照                       |
| events            | array[object]    | Agent 交互事件记录（`agent_request` / `agent_response` 事件） |
| error             | string \| null   | 执行失败时的错误信息                                      |

---

### 典型调用流程

```
                        ┌─────────────────────────┐
                        │ POST /orchestrate/search │  ← 检索工作流
                        │ { intent: "...", top_n } │
                        └──────────┬──────────────┘
                                   │ 返回 TopN 摘要列表
                                   ▼
                    ┌──────────────────────────────┐
                    │ 调用方选择目标 ID              │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │ 已有匹配           │                     │ 无匹配
              ▼                    │                     ▼
   ┌──────────────────────┐       │          ┌─────────────────────┐
   │ GET /orchestrate/    │       │          │ POST /orchestrate/   │
   │   execute/{id}       │       │          │   intent             │
   │ SSE 执行指定工作流    │       │          │ 意图编排→保存→返回    │
   └──────────┬───────────┘       │          └──────────┬──────────┘
              │                   │                     │
              └───────────────────┼─────────────────────┘
                                  │ 或直接走一站式：
                                  ▼
                    ┌──────────────────────────────┐
                    │ POST /orchestrate/execute     │
                    │ 自动检索 + 执行 / 生成 + 执行  │
                    │ (SSE 实时推送)                │
                    └──────────┬───────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │ GET /executions/{id}          │
                    │ 查询执行结果详情               │
                    └──────────────────────────────┘
```
