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

# A2A-T 多智能体编排中心

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-20.19+-green.svg" alt="Node.js"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-orange.svg" alt="License"></a>
</p>

<p align="center">
  <strong>基于 A2A-T 协议的多智能体可视化编排平台。</strong>
  <br>
  A visual orchestration platform for multi-agent collaboration via the A2A-T protocol.
</p>

<p align="center">
  <a href="./README.md">English</a>
</p>

---

## 概述

编排中心是一个面向多智能体（Agent）协作的可视化编排平台，提供拖拽式工作流设计器、异步执行引擎和 A2A-T 协商集成。

**典型场景：** 电信网络保障工作流、RAN 节能编排、SPN 故障处理流水线、企业多智能体自动化。

```mermaid
sequenceDiagram
    actor User as 用户
    participant FE as 编排中心前端<br/>(React :3003)
    participant BE as 后端 :5001<br/>(FastAPI)
    participant LLM as 大模型
    participant Reg as 注册中心
    participant Host as Host Agent 执行宿主
    participant Agt as Agent 服务

    rect rgb(240, 248, 255)
        Note over User, Reg: 1. Agent 发现
        FE->>+BE: GET /rest/v1/orchestrate/agent-cards
        BE->>Reg: 获取 AgentCard 列表
        Reg-->>BE: AgentCard[]
        BE-->>-FE: agent-cards JSON
        FE-->>User: 展示可用 Agent 列表
    end

    rect rgb(255, 250, 240)
        Note over User, Reg: 2. 工作流创建（三种方式）
        alt 2a. PDF 导入
            User->>FE: 上传 PDF
            FE->>+BE: POST /rest/v1/orchestrate/parse-pdf
            BE->>LLM: 解析章节与任务
            LLM-->>BE: 结构化 PreFlow
            BE-->>-FE: PreFlow JSON
            FE->>BE: POST /rest/v1/orchestrate/generate-from-preflow
            BE->>LLM: 从 PreFlow 生成 PSOP
            LLM-->>BE: PSOP 工作流
            BE-->>FE: PSOP JSON
        else 2b. 拖拽编排
            User->>FE: 拖拽 Agent、连接节点、配置条件
            FE->>FE: 构建工作流图（React Flow）
        else 2c. 自然语言意图
            User->>FE: 输入意图文本
            FE->>+BE: POST /rest/v1/orchestrate/generate-from-intent
            BE->>Reg: 获取 AgentCard 列表
            Reg-->>BE: AgentCard[]
            BE->>LLM: 从意图生成 PSOP
            LLM-->>BE: PSOP 工作流
            BE-->>-FE: PSOP JSON
        end
    end

    rect rgb(240, 255, 240)
        Note over User, Reg: 3. 保存工作流
        User->>FE: 点击保存
        FE->>+BE: POST /rest/v1/orchestrate/workflows<br/>{psop: {...}}
        BE->>BE: 校验 PSOP（Pydantic）
        BE->>BE: 持久化（File JSON / PostgreSQL / MySQL）
        BE-->>-FE: {workflow_id: "..."}
        FE-->>User: 保存成功
    end

    rect rgb(255, 245, 255)
        Note over User, Agt: 4. 执行工作流
        User->>FE: 点击执行
        FE->>+BE: GET /rest/v1/orchestrate/execute<br/>?psop_id=xxx&user_intent=...&lang=zh
        BE->>Reg: 获取 AgentCard
        Reg-->>BE: AgentCard[]
        BE->>BE: 捕获所选 PSOP 快照
        BE->>Host: A2A-T 下发意图、PSOP ID 与快照
        Note over Host: 校验快照；SDK 驱动其 DAG，不重新检索
        loop 工作流步骤与任务
            Host->>Agt: A2A/A2A-T 任务或协商
            Agt-->>Host: 结果与状态
            Host-->>BE: TaskUpdate metadata.__sdk_event__
            BE-->>FE: SSE data: SDK 事件
        end
        BE->>BE: 保存有界事件尾部与最终状态
        BE-->>FE: complete/error/cancelled 或异常 EOF
        BE-->>-FE: 传输 EOF（不保证 close 事件）
        FE-->>User: 执行完成
    end
```

## 核心能力

| 能力 | 说明 |
|------|------|
| **可视化编排** | 基于 React Flow 的拖拽式工作流设计器，支持自动 Dagre 布局 |
| **多模式生成** | 支持 PDF 文档导入、手动拖拽编排、自然语言生成三种工作流创建方式 |
| **A2A-T 协商集成** | workflow-engine 负责任务身份和交互生命周期，宿主回调使用当前 A2A-T 内容生成与校验接口完成业务决策 |
| **执行引擎** | `OrchestrationEngine` — 薄 A2A-T 分发通道；PSOP 工作流执行由 Host Agent（执行宿主）中的 workflow-engine SDK 承担 |
| **语义检索** | 基于自然语言意图检索历史工作流，快速复用已有流程 |
| **双 API 层** | 内部 API（`/rest/v1/orchestrate/*`）供前端调用 + 对外 API（`/api/v1/*`）供第三方集成 |
| **SSE 流式推送** | 推送执行阶段、SDK 任务/步骤/Agent 事件及 complete/error/cancelled 结果；详见 API 事件契约 |
| **可插拔存储** | 文件 JSON、PostgreSQL 或 MySQL 持久化，通过 HandlerRegistry 切换 |
| **模板市场** | 内置跨城市 SPN 诊断模板；可在 samples/workflow_templates/ 中补充已审核模板 |
| **示例 Agent** | 3 个示例 A2A Agent（Host Agent + 两个 SPN 域 Agent），用于测试和演示 |

MySQL 配置、存储边界与容器启动步骤见 [MySQL 持久化配置](docs/zh/MySQL持久化配置.md)。

SPG 批量导入、默认库执行依赖及已有示例的安全升级见 [SPG 导入](docs/zh/SPG导入.md)。默认 AN L4 卡片是规划目录，不代表业务 Agent 已部署。

PSOP 意图检索、可选的 embedding 召回开关及其降级行为见 [PSOP 检索](docs/zh/PSOP检索.md)。

## 快速开始

### 环境要求

| 组件 | 版本要求 |
|------|----------|
| Python | 3.12+ |
| Node.js | 20.19+ |

### 安装运行

```bash
# 克隆仓库
git clone https://github.com/project-openan/orchestration-center.git
cd orchestration-center

# 后端启动
python3 -m venv .venv
source .venv/bin/activate      # Linux
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
# 首次配置：仅在 server.conf 不存在时复制公开模板，不覆盖本地配置。
# 将 etc/config/models.yaml.example 复制为 models.yaml，填写模型/URL；密钥按名放入 .env。
python generate_access_password.py  # 仅打印哈希，须手动写入 server.conf 的 access_password
python -m orchestrate.start    # 端口 5001；HTTP 仍须登录

# 前端启动（新终端）
cd workflow-designer
npm install --force
npm run dev                     # 端口 3003

# （可选）启动示例 Agent
cd ..
python -m samples.start_agents_server
```

### 验证

| 服务 | 验证方式 |
|------|----------|
| 后端 | 日志输出 `Uvicorn running on http://127.0.0.1:5001` |
| 前端 | 浏览器访问 `http://localhost:3003` |
| 示例 Agent | 控制台输出各 Agent 启动信息 |

## 架构

```mermaid
flowchart TB
    subgraph frontend["前端"]
        wd["工作流设计器<br/>React 18 + Vite + Tailwind<br/>端口 3003"]
    end

    subgraph backend["编排后端 (端口 5001)"]
        direction TB
        api["双 API 层<br/>内部 /rest/v1/orchestrate/*<br/>对外 /api/v1/*"]
        domain["核心领域<br/>PSOP 生成 · 意图生成<br/>语义检索 · 发布"]
        engine["OrchestrationEngine<br/>薄 A2A-T 分发通道<br/>SSE 事件转发"]
    end

    subgraph storage["存储"]
        direction LR
        file[("文件 JSON")]
        pg[("PostgreSQL")]
    end

    subgraph agents["A2A Agent"]
        direction LR
        a1["Agent A"]
        a2["Agent B"]
        a3["Agent C..."]
    end

    wd -->|"REST / SSE"| api
    api --> domain
    domain --> engine
    engine --> file
    engine --> pg
    engine -->|"A2A-T 协议"| wb["Host Agent（执行宿主）<br/>(Leader · workflow-engine SDK)"]
    wb -->|"A2A 协议<br/>+ A2A-T 协商"| a1
    wb --> a2
    wb --> a3

    style backend fill:#e1f5fe,stroke:#0288d1
    style frontend fill:#e8f5e9,stroke:#388e3c
    style storage fill:#f3e5f5,stroke:#7b1fa2
    style agents fill:#fff3e0,stroke:#f57c00
```

## API 概览

### 对外 API (`/api/v1/*`)

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/orchestrate/sop` | SOP 编排（JSON 文本或文件上传） |
| `POST` | `/api/v1/orchestrate/intent` | 意图编排 |
| `GET` | `/api/v1/orchestrate/psop/{id}` | 获取 PSOP 工作流详情 |
| `POST` | `/api/v1/orchestrate/search` | 自然语言语义检索工作流 |
| `POST` | `/api/v1/orchestrate/execute` | 自动编排+执行（SSE 流式推送） |
| `GET` | `/api/v1/orchestrate/execute/{id}` | 执行指定 PSOP（SSE 流式推送） |
| `GET` | `/api/v1/executions` | 查询执行记录列表 |
| `GET` | `/api/v1/executions/{id}` | 查询执行结果 |

### 内部 API (`/rest/v1/orchestrate/*`)

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/workflows` | 查询工作流列表 |
| `GET` | `/workflows/{id}` | 获取工作流详情 |
| `POST` | `/workflows` | 创建工作流 |
| `DELETE` | `/workflows/{id}` | 删除工作流 |
| `POST` | `/parse-pdf` | 解析 PDF SolutionPackage 提取 PreFlow |
| `POST` | `/generate-from-preflow` | 从 PreFlow 生成 PSOP |
| `POST` | `/generate-from-intent` | 从意图生成 PSOP |
| `POST` | `/retrieve-by-intent` | 按意图检索工作流 |
| `POST` | `/retrieve-topn-by-intent` | 按意图检索 Top-N 工作流 |
| `GET` | `/agent-cards` | 查询可用 Agent 列表 |
| `GET` | `/solution-packages` / `/solution-packages/{pdf_filename}` | 方案包列表/详情 |
| `DELETE` | `/solution-packages/{pdf_filename}` | 删除指定方案包，不是批量删除 |
| `PUT` / `DELETE` | `/agent-cards/{organization}/{name}` | 管理员卡片写操作代理 |
| `GET` | `/dispatch` | 必填 intent、agent_name，可选 lang；SSE |
| `GET` | `/templates` | 查询工作流模板列表 |
| `POST` | `/templates/{id}/import` | 从模板导入工作流 |
| `GET` | `/execute` | 启动工作流执行（SSE 流式推送），参数：`psop_id`、`user_intent`、`lang` |
| `GET` | `/execution-records` | 查询执行记录列表 |
| `GET` | `/execution-records/{id}` | 获取执行记录详情 |
| `DELETE` | `/execution-records/{id}` | 删除执行记录 |
| `POST` | `/sandbox/{workflow_id}/run` | 沙箱验证/模板；详见 API 第 8 节 |
| `GET` | `/sandbox/verifications` | 沙箱验证/模板；详见 API 第 8 节 |
| `GET` | `/sandbox/verifications/{id}` | 沙箱验证/模板；详见 API 第 8 节 |
| `GET` | `/sandbox/verifications/{id}/events` | 沙箱验证/模板；详见 API 第 8 节 |
| `DELETE` | `/sandbox/verifications/{id}` | 沙箱验证/模板；详见 API 第 8 节 |
| `GET` | `/sandbox/templates/{workflow_id}` | 沙箱验证/模板；详见 API 第 8 节 |
| `PUT` | `/sandbox/templates/{workflow_id}` | 沙箱验证/模板；详见 API 第 8 节 |

完整规范：[API 参考](docs/zh/编排中心API参考.md)

按 ID 执行会将所选 PSOP ID 与独立快照下发给 Host Agent，不再按意图重新检索。`user_intent` 仅提供执行上下文，不改变工作流选择；快照捕获后的工作流编辑仅影响后续执行。详见 API 第 5 节。

## 安全

编排中心提供多层访问控制：

### 前端登录（内部 API）

内部 API（`/rest/v1/orchestrate/*`）受令牌认证保护。根据 `persistence_mode` 支持两种模式：

**数据库模式（`persistence_mode=postgresql` 或 `mysql`）**：

- 明文密码通过 TLS 发送到后端，使用版本化 bcrypt 哈希保存；旧哈希在成功登录后升级。
- SQL 空用户库首次启动需注入 `OC_ADMIN_INITIAL_PASSWORD` 或配置 `admin_initial_password_file` 来创建 admin；无硬编码默认密码，已有账号不会重置。
- 自助注册默认关闭；显式设置 `auth.register.enabled=true` 后才可注册。
- 密码要求至少 8 位，且至少包含以下两类字符：数字、大写字母、小写字母、特殊字符。该策略在服务端强制校验（`common/util/password_util.validate_password_complexity`），而不仅仅是前端界面提示。

**文件模式（`persistence_mode=file`）**：
- 通过 `server.conf` 的 `access_password` 配置单一密码。
- 用户名固定为 `admin`。
- 不支持注册。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `access_password` | 文件模式登录密码的版本化哈希，兼容旧 SHA-256。留空是未配置账号认证，不是关闭认证；默认 HTTP/HTTPS 均拒绝以此配置启动。 | 空（未配置） |
| `access_token_ttl` | 会话令牌有效期（秒）。 | `43200`（12小时） |
| `persistence_mode` | `postgresql` 或 `mysql` 启用数据库用户管理；`file` 使用配置密码认证。 | `file` |

前端提交原始密码，由后端验证已存哈希；生产公共入口应使用 HTTPS 保证传输机密性。登录下发 HttpOnly、SameSite=Lax Cookie，Secure 取决于 `public_scheme` 或可信请求协议，而非仅后端 TLS。浏览器 JavaScript 不读取 Token，EventSource/SSE 通过 Cookie 认证，不将 Token 放入 URL。内部 API 也接受显式 Bearer，Authorization 优先于 Cookie。

Cookie 只会在**同源**请求中被携带。当前提供的两种部署方式——docker-compose 中前后端都在 nginx 之后，以及 `npm run dev` 时 Vite 开发服务器自带的 `/api/orchestrate` 代理——都让前端与本 API 处于同一来源，因此这一点是透明的。若手动配置为直连 IP 部署（前后端确实处于不同源），则需要将 `CORS_ORIGINS` 设置为前端的确切来源（而非默认的 `*`，因为它无法与带凭证的请求组合使用），Cookie 才能跨源生效。

> **会话存储仅限单进程。** 令牌保存在运行中 Python 进程的内存字典中。若以多个 `uvicorn` worker 运行，或在负载均衡后部署多个副本，会间歇性地拒绝本应有效的令牌——因为某个 worker 签发的令牌对其他 worker 不可见。每次进程重启也会导致所有活动会话登出（鉴于令牌本身有 TTL，这本身无害，但仍需提前预期）。当前内置的两条启动路径（`orchestrate/start.py`）都是单进程运行，因此默认情况下不会触发此问题——但如果之后需要多 worker 或多副本部署，必须先将会话存储迁移到共享后端（例如现有的 PostgreSQL 数据库，或 Redis）。

生成密码哈希（file 模式）：
```bash
python generate_access_password.py
```

### TLS/HTTPS

| 配置项 | 说明 |
|--------|------|
| `enable_https` | 启用 HTTPS。 |
| `verify_client` | 要求客户端证书（mTLS 双向认证）。未设置或设置为除字面量 `false` 以外的任何值时，默认要求证书；只有 `server.conf` 中显式写明 `verify_client=false` 才会关闭校验。 |
| `ssl_certfile` | 服务器证书路径。 |
| `ssl_keyfile` | 服务器私钥路径（加密存储）。 |
| `ssl_ca_certs` | CA 信任库，用于校验客户端证书。 |
| `client_verify_server` | 出站 HTTPS 调用（如访问注册中心）时是否校验对端证书。公开模板及主服务工厂默认 `true`。 |

生成自签名证书（RSA 3072，满足证书校验要求）：
```bash
python -m generate_selfsign_cert etc/ssl serverAuth
```

新生成的 TLS 证书默认带 SAN：`DNS:localhost`、`IP:127.0.0.1`、`IP:::1`。
部署到其他地址时，用可重复的 `--dns` / `--ip` 指定实际访问地址；显式选项会替换默认 SAN 列表：

```bash
python -m generate_selfsign_cert etc/ssl-new serverAuth --dns orch.example.test --ip 192.0.2.10
```

SAN 必须与客户端 URL 的主机匹配，IP 必须使用 `--ip`，仅设置 CN 或信任证书不能解决 SAN 缺失。
旧证书不会自动更新；工具拒绝覆盖已有证书或私钥。已有部署请在新目录生成，备份并部署匹配的
证书/私钥后重启服务；需要重新分发信任证书的客户端应同步更新。不要覆盖用于校验客户端身份的 CA 信任库。
`dataSigning` 不添加 TLS SAN，也不接受命令行 SAN 选项。

**启用 HTTPS 步骤：**

1. 生成证书（见上方命令）。`serverAuth` 会直接产出 `server.conf` 期望的部署文件
   （`server.cer`、`trust.cer`、`server_key.pem`、`cert_pwd`）；加 `--plain-key` 还会额外
   生成 Nginx 使用的未加密私钥 `server_key_nopass.pem`。无需手工复制或创建密码文件。
   口令默认路径也为 `etc/ssl/cert_pwd`；原始文件、部署副本和客户端文件均禁止覆盖。
   `cert_pwd` 为明文，整个目录需按敏感凭据保护；Windows 使用服务账号 ACL 限权。

2. 修改 `etc/conf/server.conf`：
   ```ini
   enable_https=true
   verify_client=true           # TLS 要求客户端证书；false 只关闭此项校验，
                                 # 不会关闭账号认证。
   agent_registry_url=https://127.0.0.1:5000   # 如果注册中心也用了 HTTPS
   ```

3. 在 `etc/conf/server.conf` 中设置 `client_verify_server=false`，跳过对其他服务（如注册中心）的证书校验（自签名证书场景）。

4. 重启后端：`python -m orchestrate.start`（或 `systemctl restart orchestration-center`）

5. 如果使用 Nginx 反向代理，将 `proxy_pass` 改为 `https://127.0.0.1:5001/` 并添加 `proxy_ssl_verify off;`。Nginx 需要未加密的私钥：
   ```bash
   openssl rsa -in etc/ssl/server_key.pem -out etc/ssl/nginx_key.pem -passin pass:<你的密码>
   ```
   然后在 nginx.conf 中：`ssl_certificate_key /path/to/etc/ssl/nginx_key.pem;`

### 外部 API 保护

默认账号认证（无需配置 mode；`auto` 保留为兼容别名）使用与网页登录相同的账号。调用 `POST /api/v1/auth/token`，JSON 提交 `{"username":"admin","password":"<你的密码>"}`，返回 `access_token`、`token_type: "Bearer"`、`expires_in`；随后通过 `Authorization: Bearer <access_token>` 访问 `/api/v1/*`。Cookie 单独携带及 URL Token 均不授权公开 API。`POST /api/v1/auth/logout` 撤销该 Bearer。网页/API 共用会话有效期和存储，改密、删除账号撤销该账号全部会话；强制初次改密需先通过网页完成。两种登录共用每 IP 限流。这是自有账号登录接口，不是 OAuth2 授权服务器。

HTTP 与 HTTPS 默认采用同样的账号认证。服务端 `verify_client=false` 或调用方 `verify=False` 不会关闭它；`verify_client=true` 还额外要求 TLS 客户端证书。旧直连接入可显式选 `bearer`（至少 32 字节的固定 `ORCH_API_TOKEN`）、`mtls`（HTTPS 验证客户端证书）或 `custom`，不自动回退。Nginx/Vite 代理的公开 API 始终验证原用户 Bearer，不能借代理证书放行匿名访问。详见[传输配置](docs/transport-runtime.md)。

### 认证接口

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/auth/token` | 与网页登录相同账号，返回 Bearer，不设置 Cookie |
| `POST` | `/api/v1/auth/logout` | 撤销显式传入的账号 Bearer |
| `POST` | `/rest/v1/orchestrate/auth/login` | 使用用户名 + 密码登录，设置会话 Cookie |
| `POST` | `/rest/v1/orchestrate/auth/register` | 注册新用户（仅 PostgreSQL/MySQL 模式） |
| `POST` | `/rest/v1/orchestrate/auth/logout` | 撤销会话令牌并清除其 Cookie |
| `GET` | `/rest/v1/orchestrate/auth/check` | 检查认证状态、令牌有效性及注册可用性 |
| `GET` | `/rest/v1/orchestrate/auth/users` | 列出所有用户（仅 PostgreSQL/MySQL 模式） |
| `DELETE` | `/rest/v1/orchestrate/auth/users/{username}` | 删除用户（admin 不可删除） |


## 配置速查

| 配置文件 | 用途 |
|----------|------|
| `etc/conf/server.conf` | 服务 IP、端口、TLS 证书、持久化模式、注册中心地址、登录密码哈希、下游服务端证书校验策略 |
| `etc/conf/server.properties` | TLS 密码套件、流控参数、连接限制 |
| `etc/conf/db/postgresql.json` | PostgreSQL 连接配置——已加入 .gitignore；复制 `etc/conf/db/postgresql.json.template` 作为起点（仅 `persistence_mode=postgresql` 时需要） |
| `etc/conf/db/mysql.json` | MySQL 连接配置——已加入 .gitignore；复制其 `.template`，通过 `MYSQL_PASSWORD` 注入密码，或全部使用环境变量；见 [MySQL 持久化配置](docs/zh/MySQL持久化配置.md) |
| `.env` | 本地密钥 — 已加入 gitignore；模型定义见 `etc/config/models.yaml`。协商 SDK 也直接从这里读取 `A2AT_*` 变量（见下文） |
| `etc/config/README_zh.md` | LLM 配置指南 |

## LLM 配置

模型定义放在本地（已加入 gitignore）的 `etc/config/models.yaml`，密钥从进程环境变量或仓库根目录的 `.env` 获取，进程环境优先。`models:` 下的每个键是一种能力（`chat`、`embed`、`rerank`，或由已注册 Profile 支持的其它名称）；条目中用 `model`、`url` 描述端点，并用 `api_key_env` 填写**保存密钥的环境变量名**——文件中不写密钥。兼容 OpenAI 的接口使用默认的 `openai_compatible` profile（`openai` 为旧别名）；AOC 签名接口使用 `aoc_signed` profile，并在 `auth` 下填写 `app_key_env`、`app_secret_env`。完整说明见 [LLM 配置指南](etc/config/README_zh.md)、[`models.yaml.example`](etc/config/models.yaml.example) 和 [`.env.example`](.env.example)。

现有 `.env` 中的模型配置运行 `python -m scripts.migrate_llm_config` 迁移；仍在旧 JSON 中的配置运行 `python -m scripts.migrate_legacy_llm_json`。两种方式都不会输出密钥；遇到冲突会中止，旧 JSON 的自定义协议模板需先实现 Profile。

## A2A-T SDK 集成

本项目集成了 workflow-engine SDK，用于 Host Agent（执行宿主）的工作流执行和 fulfillment 协商。工作台业务代码
使用 A2A-T SDK 的当前内容生成与校验接口，并从仓库根目录 `.env` 读取
`A2AT_LLM_PROVIDER`、`A2AT_LLM_MODEL`、`A2AT_LLM_API_KEY`、`A2AT_LLM_BASE_URL`：

```env
A2AT_LLM_PROVIDER=openai
A2AT_LLM_MODEL=deepseek-chat
A2AT_LLM_API_KEY=<your-api-key>
A2AT_LLM_BASE_URL=https://api.deepseek.com
```

`A2AT_LLM_PROVIDER` 选择的是 SDK 的 LLM 客户端，不是模型厂商——实际端点由 `A2AT_LLM_BASE_URL`
决定。请保持 `openai`：SDK 在每个进程都注册该名字，而其它名字（如 `deepseek`）只在编排中心后端
进程内注册，示例 Agent 会因此报 `Unknown llm provider`。

workflow-engine 不初始化已废弃的协商状态机。上述配置与上文的 `LLM_CHAT_*` 相互独立，两者之间没有自动派生关系。

## 文档导航

| 文档 | 说明 |
|------|------|
| [用户指南](docs/zh/用户指南.md) | 特性介绍、使用场景、快速入门、FAQ |
| [API 参考](docs/zh/编排中心API参考.md) | 完整 REST API 规范 |
| [开发指南](docs/zh/开发指南.md) | 自定义处理器、LLM 模块、扩展开发 |
| [GCP 部署指南](docs/zh/编排中心GCP容器化部署指南.md) | 历史 GCP 指南——当前一键入口不受支持 |
| [设计文档](docs/DESIGN.md) | 系统架构与设计 |
| [前端 README](workflow-designer/README.md) | 工作流设计器技术栈与开发 |
| [LLM 配置](etc/config/README_zh.md) | LLM 配置文件说明 |

> 英文文档请参见 [docs/en/](docs/en/)。

数据库连接统一使用 `etc/conf/db/` 模板，密码由 `.env` / 环境变量引用；参见 [Database configuration / 数据库配置](docs/database-configuration.md)。旧连接配置不再作为运行时来源。

## Host Agent 与沙箱边界

编排中心负责工作流设计/存储和事件转发；Host Agent 是 SDK 执行宿主，负责业务回调和实际 DAG 执行。样例不是生产领域逻辑。Task-T 随单任务结束，Authorization-T 是一次性操作，Notification-T 通道独立且不随通知结果状态关闭，有心跳应保持，直到取消、异常断流或宿主关闭。

沙箱通过 stub 回调验证工作流结构与业务样例，不代表真实 Agent、授权系统、模型或网络已可用。验证前准备 stub 模板，运行后检查报告与事件，取消/删除接口区分运行中取消和已完成报告删除。完整路径、请求体与状态见 [API 第 8 节](docs/zh/编排中心API参考.md#8-沙箱验证接口)。

## 容器部署前置条件

根目录 Compose 是本地部署基线，不是一条命令即可验收的生产方案。需先准备共享 `openan-net`、
可访问的注册中心、`ORCH_ACCESS_PASSWORD` 哈希、`etc/config/models.yaml` 和其引用的环境秘密。
文件不存在时复制公开模板，不覆盖现场配置；运行配置、证书和真实 `.env` 不进入镜像或 Git。
根 Compose 默认后端 HTTP、注册中心 URL 为 `http://openan-registry-center:5000`，前端为
`http://localhost:3003`；这不代表服务所有启动方式都默认 HTTP，也不表示免登录。
`docker compose up -d --build` 前须核对端口、卷权限和注册中心独立 Token。
dev overlay 的样例模型仍挂载 legacy 路径，使用新目录时显式设置 `LLM_CONFIG_HOST_FILE` 为现存 YAML 文件。
HTTPS 需另配 SAN、CA、代理/探针与 mTLS 客户端身份，详见 [传输契约](docs/transport-runtime.md)。
容器健康不等于真实模型、Agent 和工作流已验收。

## 许可证

本项目基于 **Apache License 2.0** 开源协议。详见 [LICENSE](LICENSE)。
