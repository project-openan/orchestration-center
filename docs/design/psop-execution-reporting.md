# PSOP 执行结果上报

宿主通过 HTTPS POST 上报，中心确认数据库事务后返回。页面通过已有执行记录接口查询，或使用只读事件分页与 SSE。每次运行有独立的 UUIDv4 `execution_id`，任务结果按运行 ID、任务 ID 和尝试次数归集。

## 接入配置

编排中心通过 `OPENAN_EXECUTION_HOSTS` 启用上报入口。配置值是独立来源、令牌环境变量与 PSOP 授权范围的 JSON 映射。例子里的每个宿主令牌应独立生成，至少 32 字节，由部署环境注入。`psop_ids` 为已授权 ID 列表，显式使用 `["*"]` 表示授权同一中心的全部 PSOP。

```json
{
  "urn:openan:host:spn-workbench": {
    "token_env": "SPN_WORKBENCH_OBSERVATION_TOKEN",
    "psop_ids": ["fault-diagnosis"]
  }
}
```

当前读授权沿用中心和 Portal 的单域访问模型。启用前应确保这些现有会话和外部查询主体可访问该域的执行历史。机机入口使用 `OPENAN_EXECUTION_HOSTS` 中配置的宿主令牌，不能以另一宿主的 `source` 上报。账号/自定义认证模式下沿用中心现有的单域访问模型（目录当前由已认证调用方共享），PSOP 级可见范围与上报授权由后续权限管理统一实施。`OPENAN_EXECUTION_BATCHES_PER_SECOND` 默认为每宿主、每进程 20 批/秒。TLS 在反向代理终止时，需要把代理地址加入 `forwarded_allow_ips` 并转发 `X-Forwarded-Proto`，否则上报会按非 HTTPS 拒绝。

- Python 宿主用同一进程的 `ExecutionReporter(...)`，并向 `execute_psop(..., reporter=reporter)` 传入。在内置宿主进程中也可配置 `OPENAN_CENTER_EVENTS_URL`、`OPENAN_EXECUTION_TOKEN`、`OPENAN_EXECUTION_SOURCE`、`OPENAN_EXECUTION_SPOOL` 和独立的 `OPENAN_PSOP_ACCESS_TOKEN`。应装载含该 API 的 Python SDK 版本。
- Java 宿主创建一个 `ExecutionReporter`，使用 `ExecutePsop.builder().reporter(reporter)`，在宿主关闭时关闭 reporter。Spring Workbench 读取同一组上报环境变量。Java 和 Python 都需要每进程专属的持久化缓冲目录，默认容量 256 MiB，并为开始、终态与缺口保留空间。
- 宿主从既有 PSOP 读取接口获取 `revision` 和定义。中心保存、发布或启动回填时建立不可变快照，普通读取保持只读。定义存在而快照暂不可用时，响应仍返回定义并以 `revision: null` 表明暂不能上报。可用 `?revision=<revision>` 查询历史版本。
- 兼容派发优先使用已加载 PSOP 声明的宿主，旧定义可从唯一的 `SelfLoop` 宿主推导，缺少声明时由调用方指定。目标必须声明支持中心快照派发的宿主能力。Java Spring Workbench 通过独立 Task-T 入口执行并主动上报。内置 Python Host 同时启用上报与中心兼容派发时，在中心和 Host 进程配置相同的 `OPENAN_CENTER_DISPATCH_KEY`，长度至少 32 字节。Host 验证请求与中心执行记录绑定的签名后，由中心负责记账。

## HTTP 契约

向 `POST /api/v1/execution-events` 发送 `application/cloudevents+json` 或 `application/cloudevents-batch+json`。批次只能包含同一来源和同一次执行，最多 100 条、1 MiB，单条最多 64 KiB。成功返回 `200`，响应含已接收数、重复数、连续水位、最高观察序号和缺口。校验、事件去重、写入与水位更新在同一事务内完成。

事件信封使用 CloudEvents 1.0，`source` 为宿主来源，`subject` 为运行 ID，`id` 及数字字符串 `seq` 在重试时保持稳定。可选 `traceparent` / `tracestate` 与单跳 POST 的追踪头保持一致。事件前缀为 `dev.openan.workflow.`，后缀均为 `.v1`。

| 事件 | 数据要点 |
|---|---|
| `execution.started` | 序号 1，含 `psop_id` 和 `psop_revision` |
| `step.started`、`step.finished` | `step_ref`（例如 `s0`），完成时报告 outcome |
| `task.started`、`task.progressed`、`task.finished` | `step_ref`、`task_ref`（例如 `s0/t1`）、`task_id`、`attempt`。可上报脱敏摘要及应用显式允许的 `result.outputs` |
| `execution.finished` | 唯一终态，结果为 `succeeded`、`failed` 或 `cancelled` |
| `execution.gap.declared` | 用原缺失序号填入独立事件 ID。仅运行所有者可声明。该位置仍计入观察缺失，可继续推进后续任务状态 |

`task.progressed` 用受控标签表达协商与智能体交互阶段。中心兼容旧时间线事件名，宿主的默认采集不发送原始提示词、协商内容或 A2A 报文。

Spring Workbench 默认只记录状态和标识。需展示结论时，设置 `OPENAN_EXECUTION_CONTENT=on`，并在 `OPENAN_EXECUTION_OUTPUTS` 中列出允许的输出键，使用逗号分隔。

相同来源、ID 与规范化事件再次提交为成功重复。终态先到时仍接受之前的未占用序号。对永久拒收的普通事件，SDK 可用独立的缺口事件代替该序号。中心保留缺失事实。更高序号不能越过已知终态。

连续缺口超出接收窗口时，服务返回 `409 SEQUENCE_WINDOW` 以及已提交的 `contiguous_through` 和当前窗口内的 `missing_ranges`。SDK 保留本地实存事件，只补记确实缺失的序号，然后继续重放。中心明确返回 `410 EXECUTION_CLOSED` 时，该执行退出待发送队列并保留拒收记录。Java 保留执行 ID 和拒收状态，Python 把待发送文件移到拒收目录。确认按 `execution_id` 查询，旧流水的拒收不会改变新流水的确认结果。缓冲按来源和上报地址隔离，旧版未绑定地址的缓冲仍保留在原目录。

## 查询与运行边界

- 现有外部执行列表和详情及内部 `execution-records` 合并观察记录。SSE 使用中心提交游标、定期复核会话，并在接收窗口关闭且已读到尾部后结束。页面周期性使用 REST 查询，任务状态来自中心投影。
- 文件部署使用本机 `data/workflow_storage/execution_observation.sqlite3` 及 WAL。保留数据卷，并用 SQLite 一致性备份方式备份。数据库模式使用同一个中心配置的 PostgreSQL 或 MySQL。
- 接收入站窗口默认七天。当前保留关闭和删除标记，实际事件删除及长期归档需要独立保留策略。
- 这一阶段覆盖状态、结构化中间输出及脱敏时间线。附件上传、下载和对象保留随后通过统一存储接口接入。

## 本地验证

### Java SpringSpnDemo

中心以现有账号校验配置启动。将 `OPENAN_EXECUTION_HOSTS` 中的来源配置为授权 `psop_spn_cross_city_diagnosis`，例如 `{"urn:openan:host:spn-workbench":{"token_env":"SPN_WORKBENCH_OBSERVATION_TOKEN","psop_ids":["psop_spn_cross_city_diagnosis"]}}`，并注入令牌。文件模式下，仓库自带该 PSOP。若设置 `ORCH_WORKFLOW_STORAGE_DIR` 隔离联调数据，将定义复制到该目录下的 `workflow_storage/psop/`。数据库模式下，请在中心导入同一 PSOP。

在 Java Demo 进程设置 `ORCH_URL` 和中心读取凭据。将 `OPENAN_CENTER_EVENTS_URL` 指向同一中心的 `/api/v1/execution-events`，注入同一来源和上报令牌，并设置该进程专用的 `OPENAN_EXECUTION_SPOOL`。使用 HTTPS 和私有 CA 时，同时设置 `ORCH_CA_CERTS_PATH`。Demo 执行后，在**执行中心 → 执行记录**按日志中的 `execution_id` 查询。可查看工作流状态、步骤、各任务执行结果及时间线。默认采集任务结果状态，不上传诊断原文。

自动化联调使用 SpringSpnDemo 的实际入口和本地模拟 OMC。启动具有独立空执行记录库的中心后，设置 `OPENAN_TEST_DEMO_CENTER_URL`、账号登录所获的 `OPENAN_TEST_DEMO_CENTER_SESSION`、`OPENAN_EXECUTION_SOURCE`、`OPENAN_EXECUTION_TOKEN`，以及可选的 `OPENAN_TEST_DEMO_CENTER_CA`。在 Java 仓库运行以下命令。

```powershell
mvn -pl samples -am '-Dtest=SpringSpnDemoE2ETest#northboundDemoIsVisibleInCenterExecutionHistory' '-Dsurefire.failIfNoSpecifiedTests=false' test
```

### 中心与 Python SDK

从编排中心运行 `python -m pytest tests/test_execution_observation.py -q`。测试环境装载包含 reporter 的 Python SDK 后，会通过真实本机 HTTP 路径验证同一 PSOP 的两次并行执行。设置 `ORCH_POSTGRESQL_OBSERVATION_TEST_CONFIG` 或 `ORCH_MYSQL_OBSERVATION_TEST_CONFIG` 可验证对应的真实数据库。各变量是连接参数 JSON，包含 `host`、`port`、`database`、`user` 和 `password`。请使用专用测试数据库。

本机容量试验使用 8 个宿主、200 个执行、1,200 条约 1 KiB 的事件，以每秒 400 条的速率发送。应用内 HTTP 请求直达 ASGI，PostgreSQL 16 和 MySQL 8.0 运行在本机临时容器。PostgreSQL 实测每秒提交约 398 条，确认延迟 p95 为 67 ms，MySQL 分别为 357 条和 427 ms，两者均无拒收。MySQL 使用 48 个连接的测试池。这些数据包括入库确认，生产部署需另测网络、连接池、PSOP 大小和压力持续时间。
