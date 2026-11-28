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

# 意图→PSOP 编排规划评测集

本评测集衡量编排中心的**多智能体编排规划能力**：给定自然语言意图与可见的 AgentCard 池，规划产物（PSOP 工作流）是否结构合法、能力匹配、拓扑正确、约束遵循。

评测对象是 `orchestrate.core.intent_psop_generator.IntentPsopGenerator.generate_psop_from_intent()`（意图 → PSOP 一步生成链路），评分器不依赖真实执行，可完全离线运行。

---

## 1. 基准谱系（公开评测集对标）

维度设计与评分口径不是凭空构造，而是从五个公开基准提炼后适配到 A2A/PSOP 语境：

| 公开基准 | 借鉴点 | 在本评测集中的落点 |
|---|---|---|
| [PlanBench](https://arxiv.org/abs/2206.10498)（NeurIPS 2023 D&B） | 结构化规划域、并行块、长程计划、可扩展性 | `long_chain` 维度；步骤数/子任务数分级；用例 Schema 可扩展 |
| [NATURAL PLAN](https://arxiv.org/abs/2406.04520) | 自然语言规划（带完整工具上下文）、复杂度随实体数递减、solve rate | `single_step` / `ambiguous_intent` 维度；`capability_coverage` 求解率口径；长链用例实体递增 |
| [TravelPlanner](https://arxiv.org/abs/2402.01622)（ICML 2024 Spotlight，1225 条意图） | 硬约束/软约束满足率、参考计划（reference plan）而非唯一答案 | 必含技能（required）/禁用技能（forbidden）约束；`structure_pass`；17 条 gold 参考答案（非唯一正确解） |
| [τ-bench](https://arxiv.org/abs/2406.12045) | 规则遵循与越权拒绝、目标状态比对、pass^k 可靠性 | `out_of_scope_refusal` 与 `ambiguous_intent` 维度（"先不要动网络"类硬约束）；online 模式 `--k` 重复评测 pass^k |
| [WorfBench](https://arxiv.org/abs/2410.07869)（ICLR 2025，WorfEval） | 智能体工作流生成评测、子序列/子图匹配、序列 vs 图规划差距 | 拓扑评分整体框架：无环/孤岛/可达、并行扇出、条件分支、汇聚子图（layer/context_from）、技能对先后序（required_order） |

> 设计原则与 TravelPlanner 一致：**不要求与 gold 完全一致**，gold 仅作为"评分器必须接受"的参考锚点；真正评分依据是用例上标注的可验证需求。

## 2. 目录结构

```text
evals/
  README.md                     # 本文档
  run_eval.py                   # CLI：gold 自检 / pregen 离线评分 / online 在线评测
  data/
    cases.jsonl                 # 40 条评测用例（8 维度 × 5 条）
    agent_pool_telecom.json     # 电信运维 AgentCard 池（对齐 samples/agentcard，8 agent / 19 skill）
    agent_pool_generic.json     # 通用办公合成池（4 agent / 7 skill）
    gold/                       # 17 条参考 PSOP（每维度 ≥2 条，评分器自检锚点）
  output/                       # 报告输出目录（pregen/online）
  scoring/
    case_model.py               # EvalCase / AgentPool 模型与数据集校验
    topology.py                 # 步骤图检查（环、孤岛、祖先闭包、并行对）
    planner_scorer.py           # 需求评分器（CaseReport / PlannerScorer）
    report.py                   # 汇总聚合与 Markdown 渲染
    selftest.py                 # 变异自检（证明评分器有区分度）
tests/
  test_evals_planning_bench.py  # 数据完整性 + gold 全过 + 变异必败 + CLI 冒烟
```

## 3. 用例 Schema（cases.jsonl）

每行一条 JSON 用例：

| 字段 | 说明 |
|---|---|
| `id` | 用例编号（`TC-<维度>-<序号>`），pregen 模式按 `<id>.json` 对齐产物文件 |
| `dimension` | 八个维度之一（见下表） |
| `difficulty` | easy / medium / hard |
| `intent` | 自然语言意图（中文为主） |
| `agent_pool` + `agents` | 使用的 AgentCard 池与本次可见的智能体子集（规划器只见这些卡） |
| `source_benchmark` | 该用例设计所参照的公开基准标签 |
| `requirements.required_skills` | 必须出现的 (agent, skill) 指派对 |
| `requirements.forbidden_skills` | 禁止出现的技能（TravelPlanner 式硬约束） |
| `requirements.required_order` | 技能对 [A, B]：承载 A 的步骤必须是承载 B 步骤的严格拓扑祖先 |
| `requirements.structure` | min/max_steps、min_subtasks、requires_parallel、requires_branch、requires_aggregation |
| `requirements.capability_keywords` | 关键词 OR 组：每组须被某条子任务 description 覆盖（分解完整性） |
| `out_of_scope` | 越界用例标记，按拒答口径评分 |
| `gold_psop_file` | 可选参考答案路径（相对 evals/data） |

## 4. 评分口径

域内用例（`out_of_scope=false`）逐项计算，全部满足才判通过：

1. **schema_valid** — 产物可解析为 Pydantic `PSOP`；
2. **topology_valid** — 步骤图无环、无重复步骤名、无孤岛步骤（无人指向且不指向任何真实步骤）；
3. **skill_recall** — required (agent, skill) 对全部被指派；
4. **skill_precision** — forbidden 技能零出现；
5. **agent_consistency** — 每条子任务的 (agent, skill) 都真实存在于可见池（防幻觉）；技能可用 **id 或显示名**书写（与意图提示词暴露 `AgentSkill.name` 的口径一致，评分器统一归一化）；
6. **structure_pass** — 并行（单步多子任务或两步骤互不为祖先）、条件分支（≥2 个带非空 condition 的不同跳转目标，`end` 为合法终止伪节点）、汇聚（layer>0 或 context_from 非空）按需满足；
7. **order_pass** — required_order 各对的祖先关系成立（WorfBench 子序列思想的拓扑化）；
8. **capability_coverage** — capability_keywords 各组被至少一条子任务描述覆盖。

越界用例（`out_of_scope=true`）按 **refusal_ok** 评分：规划产物既不使用池内技能、也不虚构未知技能（`skill="none"` 是编排提示词约定的不可执行标记；生成失败/解析失败同样视为拒绝）。该维度用于暴露当前意图提示词未显式定义拒答行为的缺口。

## 5. 运行指南

```powershell
# 评分器自检：17 条参考答案必须 100% 通过；--selftest 附加变异自检（7 类单缺陷注入全部必须被拒绝）
python -m evals.run_eval --mode gold --selftest

# 离线评分已生成的 PSOP（目录下文件名 = 用例 id，如 TC-PAR-001.json）
python -m evals.run_eval --mode pregen --psop-dir out\psops

# 评分单个产物
python -m evals.run_eval --mode pregen --psop-file out\psops\TC-PAR-001.json --case-id TC-PAR-001

# 在线评测：调用真实 LLM 走 IntentPsopGenerator（需要 etc/config/models.yaml 配置对话模型）
python -m evals.run_eval --mode online --k 3 --limit 10
python -m evals.run_eval --mode online --dimensions parallel_fanout,conditional_branch

# 回归测试（数据完整性 + 评分器区分度 + CLI 冒烟）
pytest tests/test_evals_planning_bench.py -v
```

报告输出到 `evals/output/<mode>/report.json` 与 `report.md`；online 模式同时落盘每次生成的 PSOP（`evals/output/online/psops/`）并给出 pass^1 与 pass^k 汇总。

## 6. 质量保障

- `validate_case_against_pool` 校验每条用例的池引用、技能归属、禁用/排序技能可解析性（gold 模式与 pytest 都会执行）；
- gold 一致性：17 条参考答案对 8 项指标全绿（含显示名别名匹配用例）；
- 变异自检（`evals/scoring/selftest.py`）：删除必选技能、错配智能体、注入环、删除分支、抹掉汇聚、注入禁用技能、越界使用池内能力——七类变异必须全部被评分器拒绝，保证指标不是"橡皮图章"。

## 7. 扩展指南

1. 新增用例：在 `cases.jsonl` 追加一行（维度从 `DIMENSIONS` 中选），`required_skills` 引用的 (agent, skill) 必须存在于对应池；可选附 `gold/` 参考答案。
2. 新增智能体/技能：优先扩 `agent_pool_telecom.json` 并保持与 `samples/agentcard/` 对齐（id + name 双字段都要填）。
3. 换模型对比：同一用例集分别以不同 `A2AT_LLM_*` / models.yaml 配置跑 `--mode online --k 3`，对比 pass^1 / pass^k 与分项指标均值，即可量化提示词或模型改动对编排规划质量的影响。
4. 评测 PreFlow→PSOP 链路时，可复用 `scoring/` 全部组件，仅需为 `PsopGenerator` 增加对应 runner 模式。

## 8. 公开评测集实测（WorfBench）

自建集之外，本仓库规划能力可直接放到**公开基准原题**上实测。当前对接 [WorfBench](https://arxiv.org/abs/2410.07869)（ICLR 2025，智能体工作流生成基准，MIT 许可）：9 个任务域（wikihow / toolbench / toolalpaca / lumos / alfworld / webshop / os / seal_tools / intercodesql）共 2146 条官方 eval 题，每题含自然语言任务、候选动作列表与 gold 工作流图。

**协议适配**（忠实于官方流程，输出格式换成本仓库的 PSOP）：

1. 把每题的候选动作列表注入一个合成的 Operator AgentCard（对应官方把 action list 暴露给模型）；
2. 题目 instruction 作为自然语言意图交给 `IntentPsopGenerator` 生成 PSOP；
3. PSOP 投影为节点/边图：子任务描述为节点（执行序展开），step 级 `next` 跳转为边（步内子任务并行无边）；
4. 用 `evals/public/worf_eval.py` —— 官方 WorfEval 的纯 Python 复刻（拓扑序枚举 + 节点匹配 + LIS 序列 F1；最大权匹配 + 连通分量子图 F1）评分。

**口径说明**：官方节点匹配用 `all-mpnet-base-v2` 句向量（阈值 0.6），该模型需联网下载；本实现默认用字符 bigram 余弦替代（同为 0.6 阈值），是**更严格的保守下界**，数值会低于论文口径。Graph 指标同时报告两种模式：`official`（逐字保留参考实现索引空间的 public-edge 比较）与 `mapped`（映射后比较预测边与 gold 边，语义更合理），两者并列呈现。接入真实句向量后可通过 `worf_eval.match_nodes` 的 `sim_fn` 参数无缝替换。

**数据准备**（数据缓存放在仓库外，避免第三方数据入库）：

```powershell
curl.exe -4 -s -L -o D:\OpenAN\public-eval-cache\worfbench-main.tar.gz https://codeload.github.com/zjunlp/worfbench/tar.gz/refs/heads/main
tar -xzf D:\OpenAN\public-eval-cache\worfbench-main.tar.gz -C D:\OpenAN\public-eval-cache
# 解压后目录: D:\OpenAN\public-eval-cache\WorfBench\gold_traj\<task>\graph_eval.json
```

**运行**（`--mode mock` 用 gold 镜像工作流校准全链路，不消耗额度；`--mode online` 走真实大模型）：

```powershell
# 全链路校准（mock；9 域 × 10 条，node F1 必须 = 1.0）
python -m evals.public.run_worfbench --mode mock --per-task 10

# 在线实测：蓝区统一网关 glm-5.3-flash（密钥自动从 ~/.dsh/.credentials.yaml 注入）
python -m evals.public.run_worfbench --mode online --per-task 10
python -m evals.public.run_worfbench --mode online --tasks os,toolbench --per-task 20

# 回归测试（29 项：WorfEval 算法单元测试 + 适配器 + mock 端到端 + 真实数据解析冒烟）
pytest tests/test_evals_worfbench.py -v
```

报告输出 `evals/output/worfbench-online/report.{json,md}` 与逐题明细 `items.jsonl`。

**实测结果**（2026-11-18，每域 10 条 × 9 域 = 90 条，seed=42，89 条成功评分 + 1 条 LLM 读超时；模型：蓝区统一网关 glm-5.3-flash，平均耗时 70s/条，p50 54s）：

| 任务域 | Node F1 | Graph F1 (official) | Graph F1 (mapped) | 备注 |
|---|---|---|---|---|
| alfworld | 0.338 | 0.194 | 0.208 | 最难域；1 条 240s 读超时未评分 |
| intercodesql | 0.708 | 0.537 | 0.510 | 最佳域 |
| lumos | 0.517 | 0.326 | 0.347 | |
| os | 0.458 | 0.395 | 0.383 | 欠分解（预测 2.6 步 vs gold 4.2 步） |
| seal_tools | 0.943 | 0.285 | 0.285 | 节点近乎全对（P 0.92 / R 0.98）但结构全错 |
| toolalpaca | 0.570 | 0.466 | 0.471 | |
| toolbench | 0.687 | 0.282 | 0.287 | |
| webshop | 0.427 | 0.220 | 0.232 | |
| wikihow | 0.491 | 0.307 | 0.204 | 过度分解（12.9 步 vs gold 6.1 步） |
| **合计** | **0.574** | **0.336** | **0.327** | |

**关键发现**：

1. **序列 vs 图差距 +0.236**（Node F1 0.574 → Graph F1 0.336）——复现了 WorfBench 论文的核心结论且差距更大：模型选对子任务的能力远强于排出正确依赖图的能力。极端案例 seal_tools：节点精确率 0.923 / 召回率 0.975，图 F1 仅 0.285（任务选对、结构排错）。
2. **分解粒度失衡**是第二大误差源：wikihow 过度分解（2.1×）、os 欠分解（0.62×）。
3. **口径提醒**：节点匹配用字符 bigram 余弦替代官方 mpnet 句向量，本表数值为保守下界；官方协议下 Node F1 预期还会上浮。Graph 指标两种模式（official/mapped）数值接近，说明差异不来自参考实现的索引空间比较。

逐题明细与每条生成的 PSOP：`evals/output/worfbench-online-{a,b,c}/items.jsonl`、`psops/`；合并报告：`evals/output/worfbench-online/report.{json,md}`。

**与其他基准的对接结论**：τ-bench 需要模拟用户与数据库状态比对、TravelPlanner 需要 400 万条记录的沙盒工具环境，均无法离线复刻官方协议，暂不接入；PlanBench（blocksworld 动作序列）可按同样适配模式扩展（序列精确匹配），按需增加。

## 8.0 公开评测集选型池（2024-2026 调研）

**已接入 4 个公开基准**（统一 runner：`python -m evals.public.run_worfbench --bench <name>`；数据缓存统一在 `D:\OpenAN\public-eval-cache\<name>\`）：

| # | 基准 | 规模 | 节点表示 | 口径 |
|---|---|---|---|---|
| 1 | WorfBench（ICLR 2025） | 9 域 2146 题 | 子任务自然语言描述 | 官方 WorfEval 复刻（bigram 余弦近似，保守下界） |
| 2 | TaskBench（NeurIPS 2024） | 3 域 17,331 题（HF 7,458 / Multimedia 5,555 / Dailylife 4,318） | 子任务自然语言描述 | 序列 LIS F1 + 标记包含式子图 F1 |
| 3 | NESTFUL（IBM，Apache 2.0） | 1,861 条嵌套 API 调用序列 | 工具名（官方口径即序列匹配） | 工具名序列 F1 + 数据依赖链图 F1 |
| 4 | WorkflowBench（WorkflowLLM） | 50 条样例（全量 106,763 条在 HF `OpenBMB/WorkflowBench`） | API 名（Apple Shortcuts 代码→调用序列） | API 序列 F1 + 线性链图 F1 |

统一约定：图评分在含 START/END 标记节点的空间进行（与官方实现一致）；`--mode mock` 用 gold 镜像自检（四基准 node/graph F1 必须 = 1.0）；`--take` 取可比子集。

**其余候选（暂缓）**：

| 基准 | 机构/出处 | 规模与形式 | 官方指标 | 与意图→PSOP 契合度 | 结论 |
|---|---|---|---|---|---|
| [ToolHop](https://arxiv.org/abs/2501.02506) | 字节，ACL 2025 | 995 查询 + 3912 工具，多跳工具调用，本地可执行可验证 | 执行答案准确率（GPT-4o 49%） | ★★☆ 多跳形态契合，但官方口径需执行器 | 借形态做规划级评分 / 完整接需执行沙盒 |
| [τ²-bench](https://github.com/sierra-research/tau2-bench) | Sierra | **电信域**双控（用户与智能体都可改状态） | 终态数据库比对 pass^k | ★☆☆ 领域完美契合但需用户模拟器+状态机 | 暂缓（环境依赖） |
| [StableToolBench](https://github.com/THUNLP-MT/StableToolBench) | 清华 | 2 万+ API 工具学习，模拟 API 求解性评估 | 可解率/胜率 | ★☆☆ 需 API 模拟器 | 暂缓 |
| [BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html) | Berkeley | 函数调用（v3 多轮 / v4 agentic，含状态/成本约束） | AST/执行匹配 | ★☆☆ 测调用格式而非编排图 | 不接（错位） |
| [AgentBoard](https://arxiv.org/abs/2403.07714) | 港科大，NeurIPS 2024 | 9 环境多轮智能体，progress rate 分析 | 分步进度率 | ★☆☆ 需环境运行时 | 暂缓 |
| [MARBLE/MultiAgentBench](https://arxiv.org/abs/2503.01935) | 2025 | 多智能体协作场景 + 里程碑/表面指标 | 里程碑达成率 | ★☆☆ 需多智能体模拟器 | 暂缓（理念可借鉴到自建集） |
| [UltraTool](https://arxiv.org/abs/2401.17167) | 浙大 | 工具规划：问题→子任务分解树→工具匹配 | 分解树/工具匹配 | ★★☆ 分解树可映射 PSOP | 备选 |
| [PlanBench](https://arxiv.org/abs/2206.10498) | NeurIPS 2023 | 形式化规划域（Blocksworld 等） | 动作序列精确匹配 | ★★☆ 需操作符映射层 | 备选 |
| [NATURAL PLAN](https://arxiv.org/abs/2406.04520) | Google | 行程/会议/日历自然语言规划 | 精确匹配求解率 | ★☆☆ 产物形态错位 | 不接（借鉴维度设计） |
| [TravelPlanner](https://arxiv.org/abs/2402.01622) | ICML 2024 | 1225 意图 + 约束满足，400 万记录沙盒 | 约束通过率 | ★☆☆ 沙盒不可离线复刻 | 不接（借鉴约束式用例设计） |

**四基准在线冒烟基线**（glm-5.3-flash 蓝区网关，每域前 3 条，seed=42，2026-11-19）：

| 基准 | 冒烟题数 | Node F1 | Graph F1 (official / mapped) | 观察 |
|---|---|---|---|---|
| TaskBench | 9 | **0.674** | 0.513 / 0.546 | 三域均衡（0.63-0.71），HF 域稍难 |
| NESTFUL | 3 | **0.889** | 0.733 / 0.788 | 数学管线域，工具序列选择最容易 |
| WorkflowBench | 3 | **0.388** | 0.283 / 0.136 | 最难：17+ 候选 Apple Shortcuts API 中选对顺序 |
| WorfBench | 90（全量） | 0.574 | 0.336 / 0.327 | 序列-图差距 +0.236 |

逐题产物在 `evals/output/bench-<name>-online/`。注意：TaskBench huggingface 域个别样例 tool_steps 与 tool_nodes 数量不一致（官方数据噪声），解析器已标注 warnings；各基准 mock 自检（gold 镜像）node/graph F1 均 = 1.0。

## 8.2 编排执行能力评测（sandbox 桩执行）

规划评测之外，编排**执行**能力通过沙箱桩执行评测（`evals/public/run_execution.py`）：把各基准规划阶段产出的 PSOP 交给真实 workflow 引擎（`workflow_engine.execute_psop`）在沙箱桩运行时上执行（`orchestrate.sandbox.run_sandbox`），覆盖派发、并行扇出、汇聚上下文、条件路由与故障传播。

**指标**：dispatch_completeness（完成桩交互/计划子任务，SelfLoop 本地步不计）、step_coverage（启动步骤/计划步骤）、aggregation_order（汇聚步在执行路径中位于全部上游之后）、skill_coverage（实际派发技能/计划技能）、verdict（pass/warning/fail）；另按 12% 比例注入 error 场景测**故障优雅传播**。

**实测结果**（76 条 PSOP：自建 gold 17 + 四基准在线产物 59；glm-5.3-flash 规划，2026-11-20）：

| 基准 | 条数 | pass | warning | dispatch | step | agg_order | skill | 故障优雅 |
|---|---|---|---|---|---|---|---|---|
| 自建集（gold） | 17 | 13 | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 2/2 |
| NESTFUL | 3 | 3 | 0 | 1.000 | 1.000 | 0.833 | 1.000 | 0/0 |
| TaskBench | 9 | 7 | 0 | 0.875 | 0.875 | 0.750 | 0.875 | 1/1 |
| WorfBench | 44 | 36 | 2 | 1.000 | 1.000 | 0.718 | 1.000 | 6/6 |
| WorkflowBench | 3 | 2 | 0 | 1.000 | 1.000 | 0.750 | 1.000 | 1/1 |
| **合计** | **76** | **61** | **4** | **0.985** | **0.985** | **0.792** | **0.985** | **10/10** |

**发现**：

1. **执行引擎可靠性高**：76 条 PSOP 零崩溃；成功场景 verdict 通过率 92.4%（warning 为拒答计划等静态提示，属预期）。
2. **派发/覆盖近乎满分**：dispatch 与 step coverage 98.5%——引擎按 DAG 正确驱动并行扇出与汇聚。
3. **唯一系统性短板是 context_from 纪律**（aggregation_order 0.79，21 条无序汇聚）：规划器写下的 `context_from`/`layer` 声明引用了非图祖先的步骤，引擎按图拓扑自动推导上下文，导致声明的汇聚上下文未在执行中兑现。这是规划-执行错位的第一改进靶点：提示词应强制 `context_from` 与 `next` 边一致。
4. **故障优雅传播 10/10**：error 场景全部以 FAIL verdict + 错误事件干净收场，无悬挂、无崩溃。
5. 静态拦截 1 例：TaskBench 一条生成 PSOP 在执行前被静态校验拒绝（步数与工具节点数不一致），拦截机制有效。

运行命令：`python -m evals.public.run_execution --runs <run-dir>... --selfbuilt --fault-ratio 0.12`；报告在 `evals/output/execution-full/execution_report.json`。真实端到端（backend + 样例 SPN agents 走 A2A-T）的启动方式见仓库 README「Quick start」，可在此评测集的自建 SPN 用例上执行。

## 8.1 编排技术横向对比（同题集、可比子集）

> 本节 = 对比报告 §0 的**表 B（OpenAN 内部技术消融）**；与主流框架的分数对比（表 A）见 `evals/output/framework-comparison-report.md` §0。

在同一批 45 道题（每域 10 条中 seed 排序后的前 5 条，各技术题目完全相同）、同一评分口径下，对比 6 种编排技术（修复协议适配器后重跑，模型除注明外均为蓝区网关 glm-5.3-flash）：

| 编排技术 | 说明 | 评分/45 | Node F1 | Graph F1 | 平均耗时 |
|---|---|---|---|---|---|
| 单次生成（GLM，生产链路） | intent→PSOP 一步生成 | 44 | 0.615 | 0.418 | 57s |
| 三段流水线（GLM） | PreFlow→PSOP 式：抽取→技能匹配→组装（3×调用） | 40 | 0.634 | 0.453 | 57s |
| 生成-自修复（GLM） | 单次生成 + 一轮自我批判修正（2×调用） | 38 | 0.563 | 0.386 | 157s |
| 单次生成（DeepSeek-flash） | 同一编排链路换底座模型（直连，effort=low） | 44 | **0.638** | **0.431** | **18s** |
| 静态顺序链（无 LLM） | 工具清单按序编排 | 45 | 0.355 | 0.116 | <1s |
| 静态全并行（无 LLM） | 工具清单全并行 | 45 | 0.355 | 0.104 | <1s |

**结论**：

1. **底座模型质量 > 编排技巧**：DeepSeek-flash 用同样的单次生成编排就拿到最高分且快 3 倍（18s vs 57s）。换更便宜更快的模型是比增加编排复杂度更划算的第一步。
2. **多阶段流水线净收益≈0**：Node F1 +0.019 但失败率上升（40/45 vs 44/45，阶段 1 抽取偶发空结果），调用数 3×。与 NATURAL PLAN 论文"self-correction/few-shot 消融收益有限"的观察一致。
3. **自修复有害**：F1 下降（-0.05 node F1）、延迟 2.7×、超时错误增多——GLM 的批判轮倾向把原本正确的结构改坏。不要在生产链路开启盲修循环；若要修复，应基于执行反馈（结构校验器）而非模型自评。
4. **编排增益的下界清晰**：相对无 LLM 静态编排，LLM 编排带来 +0.26 Node F1 / +0.3 Graph F1。
5. 复现命令（每技术 3 分片并行）：

```powershell
python -m evals.public.run_worfbench --mode online --technique pipeline --per-task 10 --take 5 --output evals\output\technique-pipeline   # 加 --tasks 分片
python -m evals.public.run_worfbench --mode online --technique oneshot --models-config evals\public\models_deepseek.yaml --env-key-file .env --env-key-var DEEPSEEK_API_KEY --per-task 10 --take 5 --output evals\output\technique-deepseek
python -m evals.public.compare_techniques --label "oneshot-glm=technique-oneshot-glm" --label "pipeline-glm=technique-pipeline" --label "repair-glm=technique-repair" --label "oneshot-deepseek=technique-deepseek" --label "static-chain=technique-static-chain" --label "static-parallel=technique-static-parallel"
```

**与主流编排框架的定性对照**（基于公开文档，非实测）：

| 维度 | OpenAN 编排中心 | LangGraph / AutoGen 类 | Dify / n8n 类低代码 |
|---|---|---|---|
| 规划方式 | LLM 意图→PSOP 图（本次实测的对象） | 代码优先：图/对话编排由开发者手写 | 模板+表单驱动 |
| 执行契约 | A2A/A2A-T 协议、AgentCard 能力协商 | 进程内函数/消息传递 | HTTP/webhook 节点 |
| 结构校验 | 内建拓扑/沙箱校验器（本评测复用） | 依赖开发者自行保证 | 平台内嵌有限校验 |
| 可比性 | 本节提供可复现公开基准数字 | 需自行搭建同等评测 | 无规划能力评测 |

## 9. 引用

- Valmeekam et al. *PlanBench: An Extensible Benchmark for Evaluating Large Language Models on Planning and Reasoning about Change.* NeurIPS 2023 Datasets & Benchmarks. <https://arxiv.org/abs/2206.10498>
- Zheng et al. *NATURAL PLAN: Benchmarking LLMs on Natural Language Planning.* 2024. <https://arxiv.org/abs/2406.04520>
- Xie et al. *TravelPlanner: A Benchmark for Real-World Planning with Language Agents.* ICML 2024 (Spotlight). <https://arxiv.org/abs/2402.01622>
- Yao et al. *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains.* 2024. <https://arxiv.org/abs/2406.12045>
- Qiao et al. *Benchmarking Agentic Workflow Generation (WorfBench).* ICLR 2025. <https://arxiv.org/abs/2410.07869>（代码与数据：<https://github.com/zjunlp/WorfBench>）
