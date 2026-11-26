# SPG 导入与默认工作流库

内置的 19 套方案包和 PSOP 是**规划示例，不是自包含的业务执行环境**。
`samples/agentcard/spg_an_l4_agents.yaml` 是规划能力目录，其回环地址是占位，
不代表样例启动器会启动这些服务；启动器仍只实现已说明的 SPN 示例。
规划卡片不会为尚未实现的业务 Agent 虚构 Task-T 能力。

执行前必须部署并注册真实业务 Agent，核验业务域/技能，替换地址，配置受保护的
凭据及 TLS，再用实际卡片做沙箱校验。缺少 Task-T 扩展仍应判为准入失败。
不要通过伪造声明或关闭检查让结果变绿；Stub 成功不等于真实网管执行成功。
纯模拟示例应使用明确的合成卡片和端点，不冒充现场服务。

## PDF 与批量导入

内部上传和外部单章解析统一识别 `5. Interaction Flow` 及 `6. Interaction Flow`
等编号变体，保留 PDF 最后一页。缺少必需流程章、模型转换错误时明确失败，不将
失败提示当作 Markdown 保存；上传失败不创建方案包。上传得到 PreFlow，生成并
保存 PSOP 是后续独立步骤。

模型通过 `etc/config/models.yaml`（或 `LLM_CONFIG_FILE`）配置 chat，秘密从环境变量/
`.env` 引用。存储通过 `persistence_mode` 选择 file、postgresql 或 mysql，数据库连接
使用 `etc/conf/db/` 对应配置或环境别名；不要在命令或 PDF 中夹带凭据。

```powershell
python -m scripts.batch_spg_to_psop --pdf-dir D:/spgs --export-dir data/spg_import --dry-run
python -m scripts.batch_spg_to_psop --pdf-dir D:/spgs --export-dir data/spg_import
```

`generated` 仅表示已导出、**未入库**；`success` 表示保存成功且已从当前目标存储回读。
恢复时校验 PDF、章节、能力目录指纹及导出文件，并读取当前存储，不能只凭历史
success 跳过。dry-run 或保存失败后可复用导出结果，不重新调用模型；切换目标库
后也会重新确认是否存在。已有用户编辑不覆盖。`--force` 重新生成；没有可验证
输入指纹的旧断点记录会重新生成一次。导出目录应受保护，不要并发写同一个断点目录。

生成器默认拒绝没有合适技能的动作，即使目录中存在通用支撑技能。嵌入方只有在
明确拥有并验证兜底业务策略时，才可显式传入 `fallback_skill`。不能用“勉强相关”的
移动网/节能技能代替 IP、承载网或业务交付能力。

## 默认库与已有安装升级

三种存储模式都会幂等补充缺失的默认流程；启动播种不覆盖已存在的 ID。
方案包能跳转到流程，仅表示示例关联存在，不代表外部 Agent 已就绪。

修正了七套预置流程的错域技能，补充了无线业务交付、IP 质量意图、核心网分析等
独立规划能力。新安装直接获得修正版；已有安装不自动覆盖用户编辑，可先预览：

```powershell
python -m scripts.migrate_default_psops
```

结果为 `eligible`（可迁移）、`current`（已更新）、`missing`（未安装）或 `conflict`
（存在用户改动）。停止相关流程编辑/执行后，再添加
`--apply --backup-dir <受保护的备份目录>`。工具只替换与已知旧版**完整文档指纹**
一致的记录，先备份、再更新、再回读；用户修改一律保留并提示人工合并。
迁移不能与业务编辑并发运行：现有仓储端口没有原子的 compare-and-swap。
仅升级代码或启动服务不会自动执行迁移。

## 模型流式配置

chat 可配置 `stream: true`、`stream_total_timeout: 600`、`proxy: http://...`，
通过 `extra_body: {max_tokens: 8192}` 添加厂商选项。`timeout` 仍为 HTTP 超时，
`stream_total_timeout` 在消费 SSE 事件时检查。模型生成必须有正常
`finish_reason: stop` 或 `[DONE]`；提前 EOF、length 截断、错误帧、非 SSE 响应及
空答案均按失败处理。这是有限的模型生成流，不是状态无关的 Notification-T 订阅。

`extra_body` 不得覆盖 `model`、`messages`、`input`、`query`、`documents` 或 `stream`。
不具备聊天答案契约的 profile（如 embed/rerank）禁止开启 stream。
