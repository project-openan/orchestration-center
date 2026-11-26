# PSOP 意图检索

编排中心把用户意图解析为 PSOP 工作流（AIOps 场景），执行需要时还会返回前 N 个候选。
检索有两种模式，由 `etc/conf/server.conf` 中的 `retrieval.vector.enabled` 选择。

| 模式 | 行为 |
|---|---|
| `false`（默认） | 一次对话调用读取**整个** PSOP 目录 |
| `true` | 先用 embedding 召回，再按需重排，最后由 LLM 在候选内选择 |

```mermaid
flowchart TD
    A[用户意图] --> B{retrieval.vector.enabled}
    B -- false --> C[对整库发起对话调用]
    B -- true --> D[对意图做 embedding]
    D --> E[对照目录校准索引]
    E --> F[余弦召回，维度漂移时最多重建重试一次]
    F --> G{retrieval.vector.rerank}
    G -- true --> H[重排候选]
    G -- false --> I[保留向量顺序]
    H --> J{retrieval.vector.llm_final}
    I --> J
    J -- true --> K[只对候选发起对话调用]
    J -- false --> L[直接返回当前顺序]
    C --> M[PSOP 结果]
    K --> M
    L --> M
```

## 索引是派生缓存

PSOP 目录是唯一的真相源。embedding 索引只是缓存，可以随时删除，下次检索自动重建。

- **位置**：`retrieval.vector.index_file`，默认 `data/vector_index/psop_vectors.json`。
  属于运行时数据，不提交入库。
- **失效判定**：每个 PSOP 以「实际被嵌入的那段文本」（名称、描述、标签、用户意图、
  任务摘要）的哈希为键。被编辑过的重新嵌入，未改动的不产生网络调用，已删除的会被
  剔除，因此检索永远不会返回过期 ID。
- **模型与维度变化**：缓存记录模型名，以及模型、端点、请求模板/选项、响应映射的
  SHA-256 指纹，不保存这些配置的明文或认证凭据。指纹变化即丢弃缓存，即使维度未变。
  查询维度不符时最多整库重建并重试一次，目录未变化或进程重启也能恢复；若供应商持续
  返回不一致维度，按 `strict` 规则报错或回退全目录检索，不无限重试。
- **缓存完整性**：非法 JSON/根结构会被丢弃；长度错误、非数值、布尔值、NaN/Infinity
  等坏向量条目重新嵌入，合法条目继续复用。重建全部成功后才替换旧版本，失败不会留下
  半套索引。升级时旧版 version-1 缓存会重建一次。
- **持久化失败**：索引缺失、损坏或不可写，会重建或使用内存索引；重建仍依赖可用的 embedding 服务。
- **并发**：文件通过临时文件加 `os.replace` 原子写入。多进程各自持有内存副本、缓存
  「后写者胜」，每一轮都会对照目录校准。同一检索实例内的校准、重建、查询串行执行，
  避免并发请求观察到部分更新的索引；查询 embedding 的远程调用不持锁，可并行进行。

本特性刻意不引入向量数据库依赖：几百个 PSOP 时，进程内余弦扫描远低于 1 毫秒。
索引是缓存边界，将来在它背后接入 Milvus 适配器不需要改动检索代码。

## 配置项

| 键 | 默认值 | 含义 |
|---|---|---|
| `retrieval.vector.enabled` | `false` | 是否开启 embedding 召回 |
| `retrieval.vector.top_k` | `5` | 交给重排与终选的召回深度 |
| `retrieval.vector.min_score` | `0.0` | 保留候选的最低余弦相似度 |
| `retrieval.vector.rerank` | `false` | 用 `rerank` 模型重排候选 |
| `retrieval.vector.llm_final` | `true` | 由 LLM 在候选内做最终选择 |
| `retrieval.vector.strict` | `false` | embedding 不可用时是否让检索失败 |
| `retrieval.vector.index_file` | `data/vector_index/psop_vectors.json` | 缓存位置 |
| `retrieval.llm.thinking` | `true` | `true` 保留模型默认配置；`false` 对全部检索选择调用覆写为 `thinking: {"type": "disabled"}` |

开启开关前，必须在 `etc/config/models.yaml` 中配置好 `embed` 能力。只有
`retrieval.vector.rerank=true` 时才会读取 `rerank`。
思考策略对整库检索、向量终选和故障回退一致生效，不修改共享对话客户端或模型定义。
关闭思考依赖网关支持该供应商扩展参数。

## 失败行为

| 失败情形 | 结果 |
|---|---|
| embedding 不可用且 `strict=false` | 记录告警，退回 LLM 路径回答 |
| embedding 不可用且 `strict=true` | 错误向上抛出 |
| 候选被 `min_score` 全部过滤 | 记录告警，退回 LLM 路径回答 |
| 重排不可用或返回空顺序 | 记录告警，保留向量顺序 |
| 终选调用失败、响应非法或仅返回不存在的候选 | 保留向量顺序；调用异常或未知候选时记录告警 |
| 终选返回合法空数组 `[]` | 明确无匹配，返回空结果；不强塞向量候选，也不重试整库 |
| 索引损坏或不可写 | 记录告警，重建或使用内存索引 |

基础设施故障与业务否定必须区分：embedding 端点坏掉时默认回退整库，不能被读成
「没有匹配的 PSOP」；终选明确返回 `[]` 则应尊重无匹配结论。设置 `llm_final=false`
表示主动跳过语义终选，仅返回向量/重排顺序。

## 实测成本

在内置 22 个 PSOP 的目录上，使用 `etc/config/models.yaml` 的对话模型测得：

| 配置 | 提示词 | 耗时 |
|---|---|---|
| 整库，开启思考 | 28,123 字符 | 24–27 秒 |
| 整库，关闭思考 | 28,123 字符 | 1.1 秒 |
| 候选瘦身，开启思考 | 7,818 字符 | 26.9 秒 |
| 220 个候选，关闭思考 | 269,142 字符 | 1.6 秒 |

这两条结论决定了默认值：在这个量级上，候选数量**不是**主要成本，思考才是。
`retrieval.llm.thinking=false` 只在网关接受该字段时启用，并且属于需要用你自己的
模型重新验证的延迟取舍。
