# REQ74 角色执行预览与执行接口契约（v1.0.0）

> 本文件是 REQ74 角色化编排 v1.0.0 在 P0 阶段冻结的接口契约，记录 P0–P4 的最终实现形态。设计原则见[角色化编排实施方案](角色化编排实施方案.md)；验收状态见[角色化编排开发进度](角色化编排开发进度.md)。

## 范围与设计原则

- **预览与执行共用同一套解析规则**：预览复用正式解析器的全部规则（候选资格、授权、范围、技能、优先级、改选），两条路径不会漂移。
- **预览只读**：不创建业务传输、不登录 Agent、不调用 LLM、不执行任务、不写执行记录、不冻结正式 execution_id。
- **执行必须携带确认摘要**：交互式角色流程以"先预览、后确认"为准，执行请求必须携带新鲜预览返回的 `resolution_fingerprint`。
- **身份不取自请求**：请求声明的 `caller_id` 永不被信任，绑定中间件认证身份（`bind_resolution_identity`）。
- **能力与认证分离**：`ORCH_ROLE_DISPATCH_KEY` 只认证消息来源，不开启能力；角色执行由部署准入门禁控制，本版本无"业务已认证"旁路。

## 接口

### POST /rest/v1/orchestrate/role-execution/preview

只读预览。加载已保存模板、已批准目录、实例注册表与当前卡片，返回逐选择单元的诊断与（当全部单元可解析时）确认摘要。

请求体（`RolePreviewBody`）：

```json
{
  "psop_id": "已保存的角色工作流模板 ID（必填）",
  "scope": "tenant/site/business_object，可选",
  "authorized_instance_ids": ["实例子集；只能收窄服务端授权集"],
  "task_overrides": {"task_id": "instance_id"},
  "group_overrides": {"binding_group": "instance_id"},
  "tie_break": "error | instance_id"
}
```

响应 `data`（`RolePreviewResponse`）：

```json
{
  "psop_id": "...", "psop_name": "...",
  "template_fingerprint": "...", "catalog_version": "...",
  "config_version": "...", "policy_version": "...",
  "execution_scope": "t/s/b", "caller_id": "中间件认证身份",
  "units": [{
    "unit_id": "task:<task_id> | group:<binding_group>",
    "binding_group": null,
    "task_ids": ["..."],
    "required_skills": [{"task_id": "...", "role_id": "...", "role_version": "...", "skill_id": "..."}],
    "current_selection": {"instance_id": "...", "agent_name": "...", "priority": 1, "selection_reason": "..."},
    "candidates": [{"instance_id": "...", "agent_name": "...", "priority": 1}],
    "exclusions": [{"instance_id": "...", "reasons": ["SKILL_GAP"]}, {"instance_id": null, "reasons": ["NOT_AUTHORIZED"]}]
  }],
  "issues": [{"code": "AMBIGUOUS_BINDING", "message": "...", "task_ids": ["..."], "binding_group": null}],
  "can_execute": true,
  "resolution_fingerprint": "64 位十六进制（全部单元可解析时才有）",
  "execution_admission": {"allowed": true, "reasons": []}
}
```

展示安全：只有调用者被授权使用的实例会被具名；授权天花板之外的排除实例折叠为单条聚合 `NOT_AUTHORIZED` 条目，名称、端点与能力细节一律不出现。

### POST /rest/v1/orchestrate/role-execution/execute

确认后执行，SSE 响应（与 legacy GET 条目同一事件流）。`RoleExecuteBody` 在预览请求字段之上追加：

```json
{
  "user_intent": "运行期意图（可选，缺省取模板名）",
  "target_agent": "目标 Host Agent 名称（可选，缺省取服务端配置）",
  "lang": "zh | en（可选）",
  "confirm_fingerprint": "来自新鲜预览的确认摘要（必填，64–128 字符）"
}
```

正式解析重新读取全部可信输入、冻结编排安排；摘要不匹配时在任何传输建立之前拒绝（`RESOLUTION_MISMATCH`）。执行记录持久化 `confirm_fingerprint` 与 `overrides_applied`（含拒绝与失败记录）。

### Legacy GET 兼容条目（P2 兼容层）

内部 `GET /rest/v1/orchestrate/execute` 与外部 `GET /api/v1/orchestrate/execute/{psop_id}` 继续可用，查询参数新增：

- `task_overrides` / `group_overrides`：JSON 对象字符串（`task 或 group id -> instance id`）。
- `tie_break`：`error | instance_id`。

无需 `confirm_fingerprint`——legacy 条目保持既有行为，交互式确认仅约束新的 POST 执行入口。

### GET /rest/v1/orchestrate/role-catalog（目录展示/编辑投影）

返回 `RoleGenerationContext.projection()`：**只包含已批准条目的投影**，角色与技能均不携带 `review_status` 字段。因此前端编辑器的审批判定以成员资格为准——出现在投影中即代表该 `role_id@role_version#skill_id` 三元组已获批准；显式 `review_status: "draft"` 的条目（仅存在于原始目录发布文件）永不授权。保存合法性仍以后端 CatalogGate 读取原始目录为准。

## resolution_fingerprint 语义

- 定义在 `orchestrate/core/model/role_execution_snapshot.py`：对快照 dump（去掉 `execution_id` / `fingerprint` 字段）加策略 dump 做确定性序列化后取 SHA-256，`authorized_instance_ids` 排序后参与。
- 快照携带 `catalog_fingerprint`：执行/预览所加载目录发布内容的 SHA-256。目录版本不变但内容变化（如技能描述修订）同样改变摘要。
- `PSOP.created_at` 属于模板指纹：同一模板内容不同保存时间的指纹不同，测试需复用同一 PSOP 对象。
- 确认流程：预览 → 用户确认（可先改选并重新预览）→ 携带摘要执行 → 服务端重放规则并比对摘要。预览与执行之间任何可信输入变化（目录内容、目录、注册表、模板内容、授权集、改选）都会改变摘要并触发 `RESOLUTION_MISMATCH`。

## 部署准入门禁（P4）

角色执行默认关闭。共享决策函数 `host_agent/role_contract.py:role_execution_admitted(mode, deployment_environment)`：

| 规则 | 结果 |
|---|---|
| `role_execution_mode` 缺省/`disabled` | 拒绝 `MODE_DISABLED` |
| `role_execution_mode` 非 `disabled` 且非 `pilot` | 拒绝 `MODE_INVALID` |
| `role_execution_mode=pilot` 且 `deployment_environment` ∈ {`technical_pilot`, `development`, `testing`} | 放行 |
| 其余（含 `production` 与未识别值） | 拒绝 `ENVIRONMENT_NOT_PERMITTED` |

两侧执行点：

- **中心**：`orchestrate/runtime/instance_projection.py:resolve_execution_plan` 在解析任何工作之前检查，拒绝码 `ROLE_EXECUTION_NOT_ENABLED`（覆盖 internal/external/by-id/by-intent 全部入口）。配置键 `role_execution_mode`、`deployment_environment`（`etc/conf/server.conf`，example 文件给出默认值 `disabled` / `production`）。
- **Host**：`host_agent/runtime.py` 的角色快照分支在签名校验（`verify_dispatch`）**之前**检查 `HostAgentConfig.role_execution_admitted()`，拒绝码 `ROLE_EXECUTION_NOT_ADMITTED`。闭门主机上有效签名不会触发任何业务派发。

预览不受门禁阻断（保持只读诊断可用），但响应 `execution_admission` 报告准入状态，`can_execute = 有确认摘要且准入放行`。

## 错误码

| 码 | 层 | 含义 |
|---|---|---|
| `ROLE_EXECUTION_NOT_ENABLED` | 中心 | 部署准入门禁关闭（携带原因列表） |
| `RESOLUTION_MISMATCH` | 中心 | 确认摘要与正式重放不一致 |
| `RESOLUTION_INPUT_INVALID` | 中心 | 解析输入非法（含请求实例超出服务端授权） |
| `AMBIGUOUS_BINDING` | 解析器 | 同优先级候选并列且 `tie_break=error` |
| `INVALID_OVERRIDE` | 解析器 | 改选违反硬约束或组改选冲突 |
| `INSTANCE_SNAPSHOT_MISMATCH` | 解析器/Host | 重复实例身份或卡片快照冲突 |
| `INVALID_ROLE_SKILL` / `CATALOG_VERSION_UNAVAILABLE` | 目录门禁 | 保存/执行时角色技能引用非法或目录不可用 |
| `ROLE_EXECUTION_NOT_ADMITTED` | Host | Host 侧闭门拒绝（先于签名校验） |
| `NOT_AUTHORIZED` | 预览 | 聚合的未授权实例排除原因 |

## 前端消费（执行中心）

- `streamRoleExecution`（`workflow-designer/src/service/roleStream.js`）：`fetch` POST 消费 SSE，支持 AbortController 取消；心跳事件被忽略。
- 预览面板（`RolePreviewPanel.jsx`）：`data-testid` 依次为 `role-preview-panel`、`role-preview-unit`、`role-preview-issues`、`role-preview-candidate`、`role-preview-reset`、`role-preview-admission`、`role-execute-button`。候选按钮改选 → 带 overrides 自动重新预览 → 摘要随之刷新；"恢复自动"清除当前单元改选；摘要缺失或过期时确认按钮禁用。
- 准入关闭时面板显示拒绝原因（`execution.preview_admission_blocked`），确认按钮禁用。
- 保存工作流成功后派发 `orchestrate:workflow-saved` 事件，执行中心将对应预览置为过期。

## 测试锚点

- 契约与指纹：`tests/test_role_contracts.py`、`tests/test_role_contract_candidates.py`
- 预览：`tests/test_role_preview.py`
- 解析与确认：`tests/test_exec_engine_resolution.py`、`tests/test_execution_workflow_binding.py`
- 执行入口：`tests/test_role_execution_api.py`（含闭门证据：SSE 错误 + FAILED 执行记录）
- 准入门禁：`tests/test_role_admission.py`（矩阵、配置读取器、解析拒绝、预览报告、Host 配置/运行时闭门）
- Host 全链路：`tests/test_host_role_snapshot.py`、`tests/test_role_dispatch_closed_loop.py`
