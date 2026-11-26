<!--
Copyright (c) 2026 Huawei Technologies Co., Ltd.
All Rights Reserved.

SPDX-License-Identifier: Apache-2.0

   Licensed under the Apache License, Version 2.0 (the "License"); you may
   not use this file except in compliance with the License. You may obtain
   a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
   License for the specific language governing permissions and limitations
   under the License.
-->

# 编排中心API参考

## 使用前必读

### 简介

  编排中心是一个面向多智能体（Agent）协作的可视化编排平台，对外提供以下 RESTful API 接口，供其他系统集成调用：

  - **SOP 编排**：上传 PDF/TXT/MD 文件或提交自然语言 SOP 步骤，自动生成 PSOP 工作流。
  - **意图编排**：提交自然语言任务意图，由 LLM 自主规划生成 PSOP 工作流。
  - **检索工作流**：提交自然语言意图，匹配平台内已有工作流，返回最相关的 TopN 个工作流（含 ID、名称、描述等）。
  - **按意图检索并执行**：提交任务描述，检索已有工作流并执行，通过 SSE 推送进度与结果；无匹配时不会自动生成，默认 Host 通过 SSE `error` 报错。
  - **执行指定工作流**：根据已知的 PSOP ID 启动执行，通过 SSE 实时推送执行进度与结果。
  - **查询执行结果**：根据执行 ID 获取工作流执行记录的详细信息。

  公开集成接口使用 **`/api/v1`**。内部浏览器/沙箱接口使用 **`/rest/v1/orchestrate`**；下文完整路径不要再拼接 `/api/v1`。

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

### 认证

内部和公开 API 默认共用账号认证，提供两种账号来源：

- **数据库模式（PostgreSQL/MySQL）**：用户存储在数据库中，使用版本化密码哈希。支持用户管理；自助注册默认关闭，可通过 `auth.register.enabled=true` 显式开启。
- **文件模式**：通过 `server.conf` 的 `access_password` 配置单一密码，用户名固定为 `admin`。

HTTP 与 HTTPS 均强制认证。file 模式须配置密码哈希；SQL 空用户库首次引导须提供 `OC_ADMIN_INITIAL_PASSWORD` 或 `admin_initial_password_file`。缺配置拒绝启动，账号后端故障返回 503 而非放行匿名请求。首次在网页完成改密并重新登录后，才能获取公开 API Token。

**登录：**
```bash
curl -X POST https://127.0.0.1:5001/rest/v1/orchestrate/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<明文密码>"}'
```
密码经 TLS 明文发送，由后端负责哈希。登录成功后会话令牌通过 `HttpOnly` Cookie 下发，响应体本身不含令牌：
```json
{"code": 200, "data": {"auth_required": true, "expires_in": 43200, "username": "admin", "role": "admin"}}
```

**携带令牌的请求**（浏览器会自动携带会话 Cookie；非浏览器客户端可改用请求头）：
```bash
curl -H "Authorization: Bearer <令牌>" https://127.0.0.1:5001/rest/v1/orchestrate/workflows
```

SSE 端点（`EventSource`）使用同一会话 Cookie 认证，浏览器会自动发送；不再支持查询参数传令牌。

注册新用户（仅 PostgreSQL/MySQL 模式且已设置 `auth.register.enabled=true`）：
```bash
curl -X POST https://127.0.0.1:5001/rest/v1/orchestrate/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","password":"<明文密码>"}'
```

**程序登录（与网页相同账号，默认 `external.auth.mode=auto/user`）：**

```bash
curl -X POST https://127.0.0.1:5001/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<明文密码>"}'
```

成功响应不设置 Cookie，并带 `Cache-Control: no-store`：

```json
{"access_token":"<令牌>","token_type":"Bearer","expires_in":43200}
```

访问公开 `/api/v1/*` 时传 `Authorization: Bearer <令牌>`，Cookie 单独携带和 URL Token 均不授权。
`POST /api/v1/auth/logout` 携带该请求头撤销该 Token。改密、删除账号撤销全部会话；Token 按 TTL
过期，服务重启后需重新登录。强制初次改密的账号须先通过网页登录完成改密；两种登录共用每 IP 限流。
这是自有账号登录，不是 OAuth2 授权服务器。通过网页代理访问时路径前加 `/api/orchestrate`，保留原用户
Bearer；代理客户端证书不代表原用户。

HTTP/HTTPS 采用相同的账号认证；`verify_client=true` 额外要求 TLS 客户端证书，调用方 `verify=False`
不会关闭鉴权。显式 `bearer`/`mtls`/`custom` 旧直连接入见[传输配置](../transport-runtime.md)。

## 1. SOP 编排接口

- 典型场景

    用户持有解决方案包文档（PDF/TXT/MD 格式），或直接输入自然语言 SOP 步骤描述，需要自动生成多 Agent 协作的 PSOP 工作流。

- 功能描述

    接收 PDF/TXT/MD 文件（PDF 解析 `5. Interaction Flow`，也接受 `6. Interaction Flow` 等编号变体；保持英文主题标题，TXT/MD 直接读取全文）或 JSON 格式的 SOP 步骤文本，结合可用 Agent 列表，由 LLM 生成 PSOP 工作流并自动保存。

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

    ```http
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

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

    ```http
    POST /api/v1/orchestrate/intent HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

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

    ```http
    POST /api/v1/orchestrate/search HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

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

  详见 [PSOP 数据结构](#附录-apsop-数据结构)。

- 错误码

  | 状态码 | 说明                  |
  |--------|-----------------------|
  | 404    | 指定 ID 的工作流不存在 |
  | 500    | 服务器内部错误         |

---

## 3.6 获取工作流 BPMN 格式

- 典型场景

  需要将编排中心的已有工作流导入标准 BPMN 工具（Camunda Modeler、bpmn.io 等）进行查看或二次建模时，按 ID 获取该工作流的 BPMN 2.0 表示。

- 功能描述

  按 PSOP ID 查询工作流。实现上先通过与 3.5 相同的查询路径取出 PSOP，再在服务端将 PSOP 转换为 BPMN 2.0 XML（`orchestrate.core.bpmn_converter`），BPMN 不单独存储。转换规则：每个 PSOP step 映射为一个 `bpmn:task`（子任务的 Agent/技能写入 `documentation`），`next` 跳转映射为 `sequenceFlow`，多分支跳转生成排他网关，跳转条件生成 `conditionExpression`；文档附带 `BPMNDiagram` 图形信息，可直接渲染。

- 接口约束

  - 限流标识：`get_workflow`，速率由 `FLOW_CTL_ONE_PSOP` 配置决定。
  - 响应为 `application/xml`（BPMN 2.0 文档），不是第 1.3 节的 JSON 信封。

- 调用方法

  GET

- URI

  `/api/v1/orchestrate/psop/{psop_id}/bpmn`

- 请求参数

  | 参数名  | 类型   | 必填 | 位置 | 描述                |
  |--------|--------|------|------|---------------------|
  | psop_id | string | 是   | path | PSOP 工作流唯一标识  |

- 请求示例

  ```
  GET /api/v1/orchestrate/psop/06cb53d9-de27-4adf-9898-2eae5afcf888/bpmn
  ```

- 返回参数

  响应体即 BPMN 2.0 XML 文档（`bpmn:definitions` 根元素，含 `bpmn:process` 与 `bpmndi:BPMNDiagram`）；`Content-Disposition` 携带建议文件名（ASCII 回退 + RFC 5987 `filename*=UTF-8''`，支持中文工作流名）。

- 错误码

  | 状态码 | 说明                        |
  |--------|-----------------------------|
  | 404    | 指定 ID 的工作流不存在       |
  | 500    | 转换或服务器内部错误         |

---

### SSE 事件契约

执行接口返回 `text/event-stream`。从 `data:` 帧解析 JSON，忽略空行和 `: heartbeat` 等心跳注释。转发层保留 SDK 原始载荷，不把所有帧统一成固定字段结构。多数事件使用 `type`/`data`/`timestamp`，早期错误也可能仅带顶层 `message`；字段取决于事件生产方，不能假定总有 agent、request 或 execution_history。

| 事件族 | 含义与消费方式 |
| --- | --- |
| `start` | 搜索、加载或下发阶段，可能多次出现；存在时读取 `data.phase`。 |
| `psop_update` | `data.psop` 中的工作流快照，兼容对象或序列化 JSON。 |
| SDK 事件 | 原样转发任务、步骤、Agent、路由、协商、通知和授权等事件，不是固定十一种；未知类型应安全忽略或记录类型。 |
| `complete`、`error`、`cancelled` | 执行终态，取消不代表成功；错误说明可能在 data 或顶层 message。 |

编排中心不生成 `init`，也不保证发送命名 `event: close` 或 JSON `close` 帧。通过传输 EOF 判断连接结束；没有执行终态的 EOF 不能视为成功。心跳只表示连接活跃。这里是单任务执行流，不是与任务状态无关的独立 Notification-T 订阅。

执行记录只保存有界事件尾部（当前上限 1000），丢弃早期事件时在 events 数组头部增加 type=events_truncated、data.dropped 标记事件（最多 1000 条保留事件加该标记）。转发层不重建完整 `execution_history`，该字段可能为空，不能承诺完整回放。

### 解析示例（Python）

先通过账号登录取得 `OC_TOKEN`，将 `PSOP_ID` 设置为已保存工作流 ID。下面使用本机 HTTP；HTTPS 设置 `OC_BASE_URL`，通过 `REQUESTS_CA_BUNDLE` 信任部署 CA。监听器开启 mTLS 时还需提供客户端证书/私钥。生产不要关闭服务端证书校验。

```python
import json
import os
from urllib.parse import quote
import requests

base = os.environ.get("OC_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
psop_id = quote(os.environ["PSOP_ID"], safe="")
terminal = False
with requests.get(
    f"{base}/api/v1/orchestrate/execute/{psop_id}?lang=zh",
    headers={"Authorization": f"Bearer {os.environ['OC_TOKEN']}"},
    stream=True,
    timeout=(10, 60),  # 读取空闲超时；编排中心通常每 15 秒发送心跳
) as response:
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        kind = event.get("type")
        print(kind)  # 共享日志中不输出可能敏感的事件载荷。
        if kind in {"complete", "error", "cancelled"}:
            terminal = True
            break
if not terminal:
    raise RuntimeError("执行流结束，但未收到执行终态")
```

## 4. 按意图检索并执行接口

- 典型场景

    流程库中已有可用工作流，调用方只提供任务描述，由系统检索并选择流程执行。如果需要审核选择结果，请先检索再按 ID 执行。

- 功能描述

    接收任务描述，检索已有 PSOP，并把选中的 ID 与快照下发给 Host Agent 执行。此接口不会自动生成或保存新工作流。中心无匹配时仍下发裸意图，默认 Host 再次检索无结果后返回 `No matching workflow found`，通过 SSE `error` 结束本次执行并记录失败，而不是成功 `complete`。需要新流程时，先调用 `POST /api/v1/orchestrate/intent`，该接口生成并保存 PSOP；成功后读取响应 `data.id`，再调用 `GET /api/v1/orchestrate/execute/{psop_id}`。不要在收到无匹配错误后无条件重试执行接口。

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
    | task     | 是       | string | 1–10000 字符 | - | 用于检索已有工作流的任务描述，不触发生成 |
    | name     | 否       | string | 最多 256 字符 | - | 已弃用，仅兼容接收，忽略且无效果；新流程名称在意图编排接口设置 |

- 请求示例

    ```http
    POST /api/v1/orchestrate/execute HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

    {
        "task": "帮我做一次网络故障根因分析"
    }
    ```

- 响应格式（SSE 事件流）

  载荷、EOF 与心跳语义见上方 SSE 事件契约。一种可能序列是 `start → SDK 事件 → psop_update → complete → EOF`，具体顺序与次数取决于工作流。失败和取消使用 `error`/`cancelled`，不是成功 `complete`。执行记录有大小边界，不是完整会话记录。

- 错误码

    | 状态码 | 说明                              |
    |--------|-----------------------------------|
    | 422    | 请求体或字段校验失败               |
    | 500    | 流建立前发生服务错误               |
    | 503    | 并发数已满，服务器繁忙             |

    > 流建立前仍可能因认证、限流或依赖故障返回对应的 HTTP 错误；流已建立后的无匹配或执行错误通过 SSE `error` 推送，HTTP 200 不能视为执行成功。错误载荷为 `{"type":"error","data":{"error":"No matching workflow found"}}`（其他事件字段省略）。

---

## 5. 执行指定工作流接口

> **工作流绑定**：中心加载请求指定的 PSOP，将其 ID 与独立快照下发给 Host Agent，不再按意图重新检索。`user_intent` 只提供运行上下文，不会重新选择工作流；快照捕获后的编辑只影响后续执行。Host 对无效或不一致的显式元数据报错，不降级为意图检索。指定 PSOP 不存在时，在下发前返回 HTTP 404；流已建立后的 Host 校验失败通过 SSE `error` 表达。内部 `/rest/v1/orchestrate/execute?psop_id=...` 同样遵循此规则。仅按意图执行仍是独立的选择路径。

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

    与 [按意图检索并执行接口](#4-按意图检索并执行接口) 相同的 SSE 事件格式。

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

## 8. 沙箱验证接口

以下面向编辑器的接口只挂载在 `/rest/v1/orchestrate`（内部 API，会话/Bearer 认证）下，不对外部 API 暴露。

### 启动沙箱

- 方法 / URI：`POST /orchestrate/sandbox/{workflow_id}/run`
- 请求体字段：
  - `scenario`：`success`、`error`、`delay` 或 `negotiation`
  - `runtime_intent`：可选文本，最大 10,000 字符
  - `templates`：可选 Stub 模板数组，最多 200 条
  - `psop`：可选当前编辑器 PSOP 快照；存在时先校验并优先于按 `workflow_id` 加载
  - `lang`：`zh` 或 `en`，控制后端报告文案
- 响应：`202`，返回 `data.verification_id` 和 `data.status: queued`
- 错误码：`400` 快照或模板非法，`404` 工作流不存在，`429` 限流，`500` 服务错误

### 查询、详情与删除

| 方法 | URI | 描述 |
|------|-----|------|
| GET    | `/rest/v1/orchestrate/sandbox/verifications` | 查询持久化沙箱报告列表 |
| GET    | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}` | 获取已完成报告和事件 |
| GET    | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}/events` | 获取执行事件 |
| DELETE | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}` | 取消运行中的验证或删除持久化报告 |

已完成报告负载包含 `status`、`report` 和 `events`。`report` 包含结论、静态检查、执行路径、上下文链路、Stub 交互、风险、建议和可选错误信息。删除运行中验证时会先取消后台任务，再移除报告；删除操作不可恢复，响应返回 `data.deleted = <verification_id>`。

### Stub 模板存储

| 方法 | URI | 描述 |
|------|-----|------|
| GET | `/rest/v1/orchestrate/sandbox/templates/{workflow_id}` | 查询已保存模板 |
| PUT | `/rest/v1/orchestrate/sandbox/templates/{workflow_id}` | 替换已保存模板；请求体是 JSON 数组 |

模板最多 200 条；额外字段和非白名单响应变量会被拒绝。

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
POST /api/v1/orchestrate/search  →  调用方检查 TopN 结果
                 │
         ┌───────┴─────────────────┐
         │ 选择已有工作流           │ 没有可用工作流
         │                         ▼
         │          POST /api/v1/orchestrate/intent
         │          生成并保存，读取成功响应 data.id
         └──────────────┬──────────┘
                        ▼
GET /api/v1/orchestrate/execute/{psop_id}  →  SSE 执行指定流程
                        │
                        ▼
GET /api/v1/executions  →  从记录列表获取 execution_id
                        │
                        ▼
GET /api/v1/executions/{execution_id}  →  查询执行详情
```

若接受系统直接选择已有流程，可调用 `POST /api/v1/orchestrate/execute`，只传 `task`；它不是生成与执行的组合接口，无匹配时按第 4 节处理 SSE 错误。生成接口与执行接口分别受各自配额、认证及模型可用性约束，生成成功不保证执行成功。

## 前端内部接口补充

以下路径使用 `/rest/v1/orchestrate`，不是 `/api/v1`。遵循浏览器会话及允许的内部身份策略；AgentCard 写操作需要管理员权限。

| 方法 | 相对路径 | 入参与结果 |
| --- | --- | --- |
| GET | `/solution-packages` | 列出已保存方案包 |
| GET / DELETE | `/solution-packages/{pdf_filename}` | 获取/删除指定方案包，不存在返回 404 |
| PUT / DELETE | `/agent-cards/{organization}/{name}` | 管理员注册中心代理；PUT 卡片名称/组织必须匹配路径 |
| GET | `/dispatch` | 必填 intent、agent_name，可选 lang；返回单个已注册 Agent 的 SSE |

名称中的空格等必须逐路径段 URL 编码；不存在删除全部方案包的 `DELETE /solution-packages`。沙箱接口见第 8 节。
