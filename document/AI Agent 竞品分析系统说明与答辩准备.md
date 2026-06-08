# AI 驱动的竞品分析 Agent 协作系统说明与答辩准备

本文档基于比赛资料 `document/AI Agent 竞品分析.md` 和当前代码实现整理，用于快速理解系统设计、功能边界、技术亮点，并为比赛答辩准备讲解材料。

---

## 1. 比赛课题理解

### 1.1 课题目标

比赛课题要求构建一个“AI 驱动的竞品分析 Agent 协作系统”。它不是简单调用大模型生成一篇竞品分析报告，而是要模拟一个真实的数字调研小组，让多个专职 Agent 协同完成完整竞品分析流程：

1. 用户提出竞品分析需求。
2. 系统解析分析主题、行业、竞品、分析维度和报告要求。
3. 采集 Agent 从公开信息源收集资料。
4. 证据抽取 Agent 将资料结构化为可检索 evidence。
5. 分析 Agent 按维度生成可溯源 Claim。
6. 报告撰写 Agent 生成结构化报告正文。
7. 质检 Agent 交叉审查报告和证据，发现问题后触发返工。
8. 报告总结 Agent 生成执行摘要和总体结论，并进行内部 grounding QA。
9. 前端展示 DAG、日志、证据链、QA 结果和最终报告。

比赛重点强调三件事：

- 自动化：从采集、分析、撰写到质检尽量由 Agent 协同完成。
- 可信度：每条关键结论必须能够回溯到来源、证据和 Claim。
- 可观测：每个 Agent 的状态、输入摘要、输出摘要、日志和中间产物都可以查看。

### 1.2 判断标准拆解

比赛评分标准中，权重最高的是：

| 评分维度 | 权重 | 系统需要证明的能力 |
| --- | ---: | --- |
| 多 Agent 协作与输出可信度 | 35% | 角色划分清晰、DAG 流转、结构化消息、真实反馈闭环、Schema 输出、结论溯源 |
| 技术深度与工程完整度 | 25% | 端到端链路、日志 Trace、上下文管理、错误恢复、稳定性、动态 Schema |
| 业务价值与产品体验 | 20% | 效率提升、覆盖度提升、真实工作流、报告查看、证据查看、人工可干预 |
| 代码质量与文档 | 10% | 模块清晰、README、架构说明、部署说明、代码可读 |
| 合规、材料与答辩 | 10% | 公开信息采集、数据脱敏、材料完整、讲解清楚、演示直观 |

本系统的设计重点正是围绕这些评分项展开：多 Agent DAG、证据库、Claim-Evidence 绑定、QA 返工闭环、前端可视化和导出报告。

---

## 2. 系统定位

### 2.1 一句话定位

Competitive Agent 是一个面向企业产品调研场景的通用竞品分析 Agent 协作系统。用户登录后输入一句竞品分析需求，系统自动解析任务、采集公开资料、抽取证据、按维度生成分析结论、撰写报告、执行 QA 复核，并支持自动返工和报告导出。系统还提供注册、密码修改、用户任务隔离和管理员用户管理能力，便于多人使用同一套分析平台。

### 2.2 与普通大模型报告生成的区别

普通大模型报告生成通常是：

```text
用户问题 -> 大模型直接生成报告
```

本系统是：

```text
用户问题
  -> TaskPlan
  -> 动态分析维度
  -> 资料采集
  -> Evidence Chunk
  -> 向量检索
  -> 结构化 Claim
  -> 动态画像 / 对比矩阵
  -> 报告正文
  -> QA 质检
  -> 定向返工
  -> 报告总结
  -> 导出 Markdown / PDF
```

核心差异是：系统将“生成报告”拆成可检查、可返工、可审计的流水线，每一步都存储中间产物，不依赖一次性自然语言输出。

### 2.3 Demo 场景

当前系统适合展示的 Demo 场景是 AI 编程助手 / AI IDE 赛道：

```text
请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，
重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。
```

这个 Demo 能覆盖比赛要求中的主要能力：

- 多个竞品。
- 多个分析维度。
- 公开网页信息采集。
- 价格、安全、企业能力等对证据要求较高的维度。
- 多维度报告和 QA 返工。

---

## 3. 总体架构

### 3.1 架构视图

```text
Vue 3 前端
  |
  | REST API /api/v1
  v
FastAPI 后端
  |
  | 登录注册 / 用户管理 / 创建任务 / 查询任务 / 查询 DAG / 查询证据 / 查询报告
  v
MySQL 业务主库
  ^
  |
Celery Worker
  |
  | 执行 backend/app/graph/workflow.py 中的 Agent DAG
  v
Agent Workflow
  |
  | 调用外部和内部工具
  v
Firecrawl / LLM API / Embedding API / Milvus / MySQL
```

### 3.2 技术栈

后端：

- FastAPI：提供 REST API。
- SQLAlchemy：访问 MySQL。
- Alembic：数据库迁移。
- Celery + Redis：异步任务执行。
- MySQL：保存用户、任务、节点、日志、资料、证据、Claim、报告、QA。
- Milvus：保存 evidence chunk 的向量索引。
- Firecrawl：公开网页搜索与抓取。
- OpenAI-compatible LLM：任务解析、维度规划、分析、写作、QA。

前端：

- Vue 3 + TypeScript：单页应用。
- Vite：构建工具。
- Element Plus：基础 UI。
- Vue Flow：DAG 可视化。
- ECharts：指标图表。
- Pinia：状态管理。

### 3.3 用户与权限模型

系统包含两类用户：

- 普通用户：注册或由系统预置创建，只能查看和操作自己账户下的分析任务。
- 管理员：预置账号 `Admin`，除了可以管理自己的任务，还可以查看全部用户、启用或停用普通账户，并进入其他用户的任务详情执行暂停、恢复或重启。

权限边界：

- 用户必须登录后才能解析任务、创建任务、查看历史、查看报告或导出报告。
- 用户名是唯一标识，注册后不能修改。
- 用户可修改自己的密码，但不能修改用户名。
- 停用账户不能登录，管理员账户不能通过前端被停用。
- 任务 API 在后端按当前登录用户校验可见性，普通用户即使知道其它任务 id 也无法读取详情、证据、报告或 QA。

答辩时可以这样说明：系统不是单用户 Demo，而是具备基础多租户隔离能力。普通用户的数据按 `analysis_task.user_id` 隔离，管理员拥有全局运维视角，可以管理账号和跨用户处理异常任务。

### 3.4 关于 DAG 编排实现

比赛资料提到 LangGraph / CrewAI 作为推荐方向。当前系统代码中采用的是一个显式的轻量级 DAG workflow runner，核心实现位于：

- `backend/app/graph/workflow.py`
- `backend/app/services/task_service.py`

系统没有把 Agent 流程隐藏在单个大模型调用里，而是明确建模了节点和边：

- 固定节点：Planner、Dimension Prompt Planner、Collector、Evidence Extractor、Report Writer、QA、Report Finalizer。
- 动态节点：每个用户确认的分析维度都会生成一个 `dimension_analysis_*` 节点。
- 边：采集到证据抽取，证据抽取到多个维度分析 Agent，维度分析到报告撰写，报告撰写到 QA，QA 到报告总结。
- 返工边：QA 可触发 recollect、reanalyze、rewrite，前端可高亮本轮返工路径。

答辩时可以这样说明：系统使用自研轻量 DAG 调度实现了比赛要求的 DAG 流转、状态追踪、日志记录和反馈闭环。若后续需要接入 LangGraph，可以将现有节点函数和 state 迁移到 LangGraph 节点，业务边界已经拆好。

---

## 4. 核心数据流

### 4.1 主流程

```text
1. 用户输入自然语言需求
2. Planner Agent 解析 TaskPlan
3. 前端展示并允许用户确认竞品和分析维度
4. 后端创建 analysis_task 和 agent_node
5. Dimension Prompt Planner 为每个维度生成专属 prompt spec
6. Collector Agent 根据竞品和维度搜索并抓取网页
7. Evidence Extractor 清洗网页、切分 evidence chunk、调用 embedding、写入 Milvus
8. 每个动态维度 Analysis Agent 检索 evidence 并生成 Claim
9. Profile / Matrix 服务生成动态竞品画像和对比矩阵
10. Report Writer 生成结构化报告正文
11. QA Agent 检查维度分数、证据绑定、报告完整性和写作问题
12. 若 QA 不通过，按失败维度执行定向返工
13. Report Finalizer 生成执行摘要和总体结论
14. Finalizer 内部 QA 检查总结是否被 Claim 支撑
15. 前端展示报告、QA、证据和导出文件
```

### 4.2 数据对象之间的关系

```text
SourceDocument
  -> EvidenceChunk
  -> Claim
  -> ClaimEvidence
  -> Report paragraph
  -> QAResult
```

含义：

- `SourceDocument` 是原始网页资料。
- `EvidenceChunk` 是可检索、可引用的证据片段。
- `Claim` 是某个分析 Agent 生成的结构化结论。
- `ClaimEvidence` 绑定 Claim 和 EvidenceChunk。
- `Report paragraph` 通过 `claim_ids` 引用 Claim。
- 系统再根据 Claim 自动补齐 paragraph 的 `evidence_ids`。

因此最终报告里的关键段落可以回溯到：

```text
报告段落 -> claim_ids -> claim_evidence -> evidence_chunk -> source_document -> source_url
```

这正好对应比赛“每条分析结论均有据可查”的要求。

---

## 5. Agent 角色说明

### 5.1 Planner Agent

职责：

- 将用户自然语言需求解析为结构化 TaskPlan。
- 识别主题、行业、目标产品、竞品列表、分析维度、报告深度和输出语言。
- 支持自动发现竞品和自动补充分析维度。

主要产物：

- `analysis_task.task_plan_json`

答辩亮点：

- 用户不需要填写复杂表单，一句话即可启动。
- 解析后仍允许人工确认和编辑，兼顾自动化与可控性。

### 5.2 Dimension Prompt Planner Agent

职责：

- 根据 TaskPlan 中的动态分析维度，为每个维度生成专属 prompt spec。
- 每个 spec 包含 `dimension_key`、`dimension_label`、`analysis_goal`、`evidence_focus`、`must_answer`、`comparison_criteria`、`search_query_template`。

代码中对它的约束包括：

- 必须为每个字段输出一条 spec，不能新增或删除维度。
- `dimension_key` 必须等于字段 key。
- `search_query_template` 必须包含 `{competitor}` 占位符。
- 技术产品、SaaS、API、云服务、AI 工具优先使用英文搜索 query。
- 中国本土消费场景优先使用中文 query。

主要产物：

- 运行态 `dimension_prompt_specs`
- 后续 Claim 中的 `dimension_prompt_json`

答辩亮点：

- 分析维度不是写死的，系统能根据用户确认的维度动态生成维度 Agent。
- 每个维度 Agent 的目标和证据关注点不同，避免所有 Agent 使用同一套泛化提示词。

### 5.3 Collector Agent

职责：

- 根据竞品、维度和 QA 返工 query 生成采集任务。
- 调用 Firecrawl Search / Scrape 获取公开网页资料。
- 将抓取结果保存为 `source_document`。

采集资料包括：

- 官网页面。
- pricing 页面。
- docs。
- blog。
- news。
- reviews。

返工时：

- 如果 QA 判断需要 `recollect`，Collector 会进入 recollect 模式。
- recollect 模式优先使用 QA issue 中给出的 follow-up search query。

答辩亮点：

- 采集 Agent 是独立角色，不是分析 Agent 顺手搜索。
- QA 可以把证据不足的问题打回采集 Agent，形成真实反馈闭环。

### 5.4 Evidence Extractor Agent

职责：

- 清洗 `SourceDocument`。
- 切分 `EvidenceChunk`。
- 给证据片段计算可靠性分数。
- 调用 Embedding 模型生成向量。
- 将向量写入 Milvus。
- 将 metadata 和原文保存到 MySQL。

何时调用向量化模型：

- Evidence Extractor 抽取出 evidence chunk 后，会批量调用 `LLMClient.embed_texts()`。
- 每个 chunk 的 `chunk_text` 会进入 embedding API。
- 生成的向量通过 `MilvusTool.upsert_evidence_embeddings_batch()` 写入 Milvus。

失败处理：

- embedding 批量失败时会尝试拆分为单条 embedding。
- Milvus 写入失败时返回 mock vector id，MySQL 中仍保留 evidence，不会让整个报告完全中断。
- 检索时如果 Milvus 不可用，会退回 MySQL 按 `reliability_score` 获取证据。

答辩亮点：

- Milvus 只做语义召回，MySQL 才是证据原文和业务关系的权威存储。
- 即使向量库异常，系统也有降级路径，提升演示稳定性。

### 5.5 Dynamic Dimension Analysis Agents

职责：

- 每个分析维度对应一个独立 Agent。
- 每个 Agent 只负责自己的维度，不分析其它维度。
- 对每个竞品进行 evidence 检索。
- 基于 evidence 生成结构化 Claim。

输出格式要求：

```json
{
  "competitor_name": "竞品名称",
  "dimension_key": "维度 key",
  "dimension_label": "维度名称",
  "claim_text": "中文结论，必须具体且可被证据支撑",
  "evidence_ids": [1, 2],
  "confidence": 0.85,
  "risk_level": "low"
}
```

分析 Agent 检索证据规则：

1. 根据维度 prompt spec 生成 query。
2. 优先按 `task_id + competitor_name + source_type` 在 Milvus 检索。
3. 如果带 source_type 没有结果，则放宽 source_type 再检索一次。
4. 如果 Milvus 检索失败，则降级为 MySQL fallback，按 `reliability_score desc, id asc` 获取 top_k。
5. 每个 Claim 必须绑定当前检索到的 evidence id。
6. 如果模型没有返回合法 evidence id，后端会使用检索结果中的首个 evidence 兜底，避免 Claim 完全失去证据绑定。

分析 Agent 提示词核心约束：

- “你只负责一个分析维度，不要分析其它维度。”
- 必须围绕当前维度的分析目标、比较标准和必须回答问题生成结论。
- 必须基于给定 evidence。
- 只输出合法 JSON 数组。
- `evidence_ids` 只能引用提供的 evidence id。
- 返工时会附加 QA 问题、建议动作和 follow-up query，要求优先修复上一轮问题。

答辩亮点：

- 一个分析维度一个 Agent，职责边界清晰。
- Claim 是结构化输出，不是自由文本。
- Claim 带有 dimension、competitor、confidence、risk 和 evidence 绑定。

### 5.6 Dynamic Profile / Matrix Builder

职责：

- 根据 Claim 和 Evidence 生成动态竞品画像。
- 根据分析维度生成对比矩阵。

特点：

- 不依赖固定字段。
- 用户确认了哪些维度，系统就围绕哪些维度生成画像和矩阵。
- 对比矩阵单元格保留 claim ids 和 evidence ids。

答辩亮点：

- 体现动态 Schema 演化能力。
- 同一套系统可以换行业、换竞品、换分析维度。

### 5.7 Report Writer Agent

职责：

- 基于 CompetitorProfiles、ComparisonMatrices 和 Claims 生成报告正文。
- 只生成具体分析维度 section。
- 不生成执行摘要、总体结论、建议、风险提示、排名等全文总结。

报告正文 JSON 约束：

```json
{
  "title": "报告标题",
  "sections": [
    {
      "section_id": "pricing_strategy",
      "title": "价格策略",
      "paragraphs": [
        {
          "paragraph_id": "pricing_strategy_p1",
          "text": "段落正文",
          "claim_ids": [1, 2]
        }
      ]
    }
  ]
}
```

关键规则：

- 每个关键 paragraph 必须包含 `paragraph_id`、`text`、`claim_ids`。
- `claim_ids` 只能引用已有 Claim，不能编造。
- 不要求模型输出 `evidence_ids`，后端会根据 Claim-Evidence 自动补齐。

返工时：

- `partial_revision` 模式只允许重写目标失败维度。
- 不允许改写其它维度。
- 系统会将上一版目标维度 section、目标 Claim、全部 Claim 和动态画像提供给模型。

答辩亮点：

- 报告撰写和总结分离，正文更容易被维度 QA 检查。
- partial rewrite 能减少返工成本，并避免已通过维度被误改。

### 5.8 QA Agent

职责：

- 对报告正文和 Claim 进行质量检查。
- 输出整体 QA 分数、每个维度的分数、问题列表和返工建议。
- 将每个动态维度 Agent 的当前 QA 状态写入数据库。

QA 检查范围：

- 第一轮是 `full_report`，覆盖全部维度。
- 返工后是 `partial_revision`，只检查本轮返工目标维度。

QA 输出结构：

```json
{
  "passed": true,
  "score": 0.86,
  "dimension_scores": [
    {
      "target_node": "dimension_analysis_xxx",
      "dimension_label": "价格策略",
      "score": 0.75,
      "passed": true
    }
  ],
  "issues": [
    {
      "type": "weak_evidence",
      "severity": "medium",
      "message": "某维度证据较弱",
      "related_claim_id": 12,
      "related_dimension": "价格策略",
      "suggested_action": "reanalyze",
      "target_node": "dimension_analysis_xxx",
      "search_query": null
    }
  ]
}
```

QA 类型包括：

- `logic_gap`
- `unsupported_claim`
- `weak_evidence`
- `schema_incomplete`
- `writing_issue`
- `missing_evidence`

返工动作包括：

- `recollect`：证据不足，需要补采资料。
- `reanalyze`：已有证据但分析结论不充分，需要重跑维度分析 Agent。
- `rewrite`：Claim 和证据可用，但报告表达或结构需要重写。

答辩亮点：

- QA Agent 不是只给一个总分，而是给每个分析维度打分。
- 每个维度的 QA 状态持久化到 `agent_node`，可作为下一轮调度依据。
- 返工目标来自 QA 失败维度全集，避免漏掉失败维度。

### 5.9 Report Finalizer Agent

职责：

- 在维度正文完成后，生成全局总结 section。
- 当前只允许生成两个全局 section：
  - `执行摘要`
  - `总体结论`

报告顺序：

```text
执行摘要
分析维度 1
分析维度 2
...
分析维度 N
总体结论
```

Finalizer 内部 QA：

- 检查执行摘要和总体结论是否引入 Claim 中不存在的新事实。
- 检查每个 paragraph 的 `claim_ids` 是否能支撑核心判断。
- 如果正文 QA 未通过，检查总结是否说明可靠性边界。

如果 Finalizer QA 不通过：

- 系统会构造 `finalizer_revision_context`。
- 下一轮总结生成会收到具体 grounding issue。
- Prompt 会要求逐条修复问题，而不是泛泛改写。

答辩亮点：

- 报告总结 Agent 也有自己的 QA 和返工闭环。
- 全局总结不允许脱离 Claim 编造新判断。

---

## 6. QA 返工闭环详解

### 6.1 为什么要把 QA 状态写入 AgentNode

每个分析 Agent 对应一个分析维度，并在数据库中有一条 `agent_node` 记录。系统为动态维度 Agent 增加了当前 QA 状态字段：

| 字段 | 含义 |
| --- | --- |
| `qa_passed` | 当前维度是否通过 QA |
| `qa_score` | 当前维度最新 QA 分数 |
| `qa_revision_round` | 该 QA 状态来自第几轮 |
| `qa_issue_count` | 当前维度关联问题数量 |
| `qa_updated_at` | QA 状态更新时间 |

这样设计的原因：

- `qa_result` 保存历史快照，适合回放。
- `agent_node` 保存当前状态，适合调度。
- 下一轮返工时直接查询当前失败维度，避免从复杂 issue 中推断目标时漏掉某些维度。

### 6.2 失败维度的权威来源

当前系统的最终规则是：

```text
返工动作可以由 issue 决定是 recollect / reanalyze / rewrite；
但返工目标维度必须来自 QA 失败维度全集，而不是来自某几类 issue action。
```

含义：

- QA 分数失败集合决定“哪些维度必须返工”。
- issue action 只决定“这些维度用什么方式返工”。
- 如果某个失败维度没有明确 action，默认按 `reanalyze` 处理。

这解决了之前出现的问题：第一轮 QA 有 5 个维度不通过，但第二轮只对 4 个维度返工。根因是早期逻辑曾从部分 issue action 中推导返工目标，导致没有被 issue 正确绑定的失败维度被漏掉。现在目标维度来自完整的 QA 失败维度集合，不再依赖某几类 issue 的 target_node。

### 6.3 多种返工动作同时存在时的执行顺序

当失败维度中同时出现 `recollect`、`reanalyze`、`rewrite` 时，系统按以下顺序处理：

```text
1. 需要 recollect 的维度先触发 Collector 补采资料。
2. 补采后执行 Evidence Extractor，抽取并向量化新证据。
3. 分析阶段执行：
   - recollect 对应维度
   - reanalyze 对应维度
4. 构建动态画像和对比矩阵。
5. Report Writer 以 partial_revision 模式重写所有失败目标维度。
6. QA Agent 只检查本轮返工目标维度。
```

关键点：

- `recollect` 的维度补采后仍要重新分析。
- `reanalyze` 的维度直接重新分析。
- `rewrite` 的维度不需要重跑分析，但仍会进入本轮目标维度集合，最终由 Report Writer 统一 partial rewrite。
- 本轮 QA 只检查目标维度，不评价其它维度。

### 6.4 “子集约束”

比赛演示中很容易被问到：如何保证返工不会漏检或目标漂移？

系统约束是：

```text
本轮未通过维度只能是上一轮未通过维度的子集。
```

实现方式：

1. 第一轮全局 QA 覆盖全部动态维度。
2. QA 将每个维度的通过状态写入 `agent_node`。
3. 下一轮返工目标来自 `qa_passed=false` 的维度集合。
4. partial QA 只更新本轮返工维度。
5. 未参与本轮返工的维度状态不会被误改。
6. 如果某维度本轮仍不通过，它继续保留为失败状态。
7. 因此失败集合只能收缩，不会凭空漏掉。

---

## 7. RAG 与证据检索机制

### 7.1 什么时候调用向量化模型

系统在两个阶段调用模型：

1. LLM completion：
   - 任务解析。
   - 维度 prompt spec 生成。
   - Claim 生成。
   - 报告撰写。
   - QA 质检。
   - 总结生成和总结 QA。

2. Embedding：
   - Evidence Extractor 抽取 evidence chunk 后，调用 embedding 模型。
   - Analysis Agent 检索 evidence 时，会把查询语句向量化。

### 7.2 Evidence 写入 Milvus

Evidence Extractor 的向量化流程：

```text
EvidenceChunk.chunk_text
  -> LLMClient.embed_texts()
  -> embedding vector
  -> MilvusTool.ensure_collection()
  -> MilvusTool.upsert_evidence_embeddings_batch()
  -> evidence_chunk.milvus_vector_id
```

Milvus collection 字段：

| 字段 | 用途 |
| --- | --- |
| `id` | chunk id，主键 |
| `task_id` | 任务过滤 |
| `chunk_id` | MySQL evidence_chunk id |
| `competitor_name` | 竞品过滤 |
| `source_type` | 来源类型过滤 |
| `source_url` | 来源 URL |
| `embedding` | 语义向量 |

### 7.3 Analysis Agent 检索规则

检索入口是 `EvidenceRetriever.search()`。

输入：

- `task_id`
- `query`
- `competitor_name`
- `source_type`
- `top_k`

Milvus filter：

```text
task_id == 当前任务
and competitor_name == 当前竞品
and source_type == 当前来源类型
```

如果检索失败：

```text
Milvus search failed
  -> MySQL fallback
  -> 按 reliability_score desc, id asc 返回 top_k 个 evidence chunk
```

这样既保证语义相关性，又保证系统稳定性。

---

## 8. 数据库模型与可追溯性

### 8.1 主要表

| 表 | 说明 |
| --- | --- |
| `app_user` | 用户表，保存用户名、密码哈希、管理员标记和启停用状态 |
| `analysis_task` | 分析任务主表，保存用户输入、所属用户、TaskPlan 和任务状态 |
| `agent_node` | DAG 节点表，保存 Agent 状态和动态维度 QA 状态 |
| `agent_run_log` | Agent 运行日志，保存输入摘要、输出摘要、异常、检索日志 |
| `source_document` | 采集到的网页资料 |
| `evidence_chunk` | 证据片段，包含 URL、标题、来源类型、正文、可靠性分数和向量 id |
| `claim` | 分析 Agent 生成的结构化结论 |
| `claim_evidence` | Claim 和 EvidenceChunk 的绑定关系 |
| `competitor_profile` | 动态竞品画像 |
| `comparison_matrix` | 动态对比矩阵 |
| `report` | 报告 Markdown、HTML、JSON 和质量摘要 |
| `qa_result` | 每轮 QA 历史快照 |

### 8.2 溯源链路

最终报告段落中的 `claim_ids` 和 `evidence_ids` 是可追溯性的核心。

```text
report.report_json.sections[].paragraphs[]
  -> claim_ids
  -> claim.id
  -> claim_evidence.evidence_chunk_id
  -> evidence_chunk.source_url / chunk_text
  -> source_document.content_text
```

前端报告页可以展示：

- 报告正文。
- 每段关联的 Claim。
- Claim 使用的 evidence id。
- Evidence 原文片段。
- 来源 URL。

这对应评分标准中的“每条分析结论可定位到原始数据源”。

### 8.3 用户任务隔离

用户隔离依赖 `analysis_task.user_id`：

```text
当前登录用户
  -> Authorization token
  -> 后端解析 current_user
  -> analysis_task.user_id == current_user.id
  -> 返回用户自己的任务、证据、Claim、报告和 QA
```

管理员查询时可以放宽任务过滤条件：

```text
current_user.is_admin == true
  -> 可查看全部 analysis_task
  -> 可按 user_id 筛选某个用户
  -> 可对任意可见任务执行 pause / resume / retry
```

这种设计让普通用户的数据默认隔离，同时给管理员保留现场运维和异常处理入口。

---

## 9. 前端产品体验

### 9.0 登录、注册与账户管理

主要能力：

- 登录页支持账号登录和新用户注册。
- 注册时要求用户名唯一，用户名创建后不能修改。
- 登录后顶部显示当前用户，并提供修改密码入口。
- 管理员可进入“用户管理”页查看所有账户。
- 管理员可启用或停用普通账户。

产品意义：

- 系统具备多人使用基础，不再是单用户演示工具。
- 普通用户只看自己的分析资产，减少数据混淆。
- 管理员可以处理账号状态和跨用户任务异常，符合企业内部工具的运维习惯。

### 9.1 创建任务页

主要能力：

- 一句话输入需求。
- 自动发现竞品开关。
- 自动添加分析维度开关。
- 点击“解析需求”生成 TaskPlan。
- 用户可编辑竞品、维度、报告深度、语言等配置。

产品意义：

- 让用户从自然语言开始，降低使用门槛。
- 解析后保留人工确认，避免完全黑盒。

### 9.2 任务详情页

主要能力：

- 展示任务运行状态。
- 管理员查看其他用户任务时展示所属用户。
- 展示 Agent DAG。
- 展示节点运行状态、耗时、输入摘要、输出摘要、错误信息。
- 展示 worker 节点和返工高亮。
- 支持暂停、恢复、取消、重启。

产品意义：

- 让系统过程可见。
- 方便现场演示多 Agent 协作和返工路径。

### 9.3 历史记录页

主要能力：

- 普通用户只能看到自己的历史分析任务。
- 管理员默认可以看到所有用户任务。
- 管理员可按用户筛选历史任务。
- 任务卡片显示任务所属用户，便于进入详情后执行暂停、恢复或重启。

产品意义：

- 普通用户视角保持干净。
- 管理员视角覆盖全局任务队列，方便答辩现场展示多用户数据隔离和运维控制。

### 9.4 报告页

主要能力：

- 展示最终竞品分析报告。
- 报告顺序为执行摘要、分析维度、总体结论。
- 展示 QA 问题表格。
- 展示报告总结 Agent 的 QA 问题表格。
- 展示 Claim 和 Evidence。
- 支持导出 Markdown 和 PDF。

产品意义：

- 不只给出结果，还给出质量检查和证据链。
- 便于评委验证结论是否可靠。

---

## 10. 导出能力

系统支持：

- Markdown 导出。
- PDF 导出。

导出内容同步前端报告页：

- 执行摘要。
- 各分析维度正文。
- 总体结论。
- 对比矩阵。
- QA 质量摘要。
- 维度 QA 问题表。
- 报告总结 Agent QA 问题表。
- Claim 列表和 evidence 绑定。

答辩亮点：

- 系统产物不是只在网页临时展示，可以形成可交付的分析文档。
- 导出的 Markdown / PDF 与前端展示保持一致，减少口径不一致。

---

## 11. 对评分标准的逐项对应

### 11.1 多 Agent 协作与输出可信度（35%）

系统对应点：

- 多 Agent 角色清晰：Planner、Collector、Evidence Extractor、Dynamic Analyst、Report Writer、QA、Report Finalizer。
- 每个维度一个动态 Analyst Agent，职责边界明确。
- DAG 节点和边写入数据库，并在前端展示。
- Agent 间通过结构化数据传递：TaskPlan、prompt spec、EvidenceChunk、Claim、Report JSON、QAResult。
- QA 可真实触发 recollect / reanalyze / rewrite。
- Claim 必须绑定 Evidence。
- Report paragraph 必须引用 Claim。
- 最终报告可以从段落追溯到 Claim、Evidence 和 URL。

建议答辩表达：

> 我们没有让大模型一次性生成报告，而是把竞品分析拆成可追踪的多 Agent DAG。每个分析维度都有独立 Agent，输出结构化 Claim，并强制绑定 Evidence。QA Agent 不通过时会触发真实返工，不是伪闭环。

### 11.2 技术深度与工程完整度（25%）

系统对应点：

- 端到端链路完整：前端输入、后端 API、异步任务、采集、证据、向量库、分析、报告、QA、导出。
- MySQL 保存全部业务状态。
- Milvus 支持 evidence 语义检索。
- Celery + Redis 支持后台任务。
- Agent 状态、耗时、日志、错误信息可查。
- embedding / Milvus / Firecrawl 均有降级或异常处理。
- QA 返工有最大轮次控制。
- 动态 Schema 支持换行业、换维度。
- 用户、任务、报告等 API 具备登录鉴权和任务归属校验。
- 管理员具备跨用户任务查看和任务控制能力，方便系统运维。

建议答辩表达：

> 工程上我们把业务状态全部落 MySQL，把 Milvus 定位为 evidence 召回索引，把 Celery 用于后台执行。即使向量库检索失败，也可以回退到 MySQL 的可靠性排序，保证 Demo 稳定性。

### 11.3 业务价值与产品体验（20%）

系统对应点：

- 一句话生成 TaskPlan，减少人工配置。
- 自动发现竞品和自动补充维度。
- 分析维度可编辑，贴合真实产品调研流程。
- 多维度报告、矩阵和画像提升可读性。
- 证据链和 QA 问题可查看，便于人工复核。
- 导出 Markdown / PDF，形成正式分析材料。
- 支持注册、登录和修改密码，适合多人共用。
- 普通用户任务隔离，管理员可集中管理账户和处理异常任务。

建议答辩表达：

> 相比传统人工竞品分析，系统把重复的信息搜索、证据整理、结构化对比和初版报告撰写自动化。产品经理仍可以在 TaskPlan 阶段介入修改维度，保证自动化不失控。同时系统支持多用户登录和管理员运维，便于团队共享一套分析平台。

### 11.4 代码质量与文档（10%）

系统对应点：

- 后端按 API、models、schemas、services、tools、graph 分层。
- 前端按 API、components、stores、views、types 分层。
- README 已包含系统介绍、架构、API、环境变量、启动方式、测试方式。
- README 和答辩文档同步记录用户体系、权限边界和管理员操作流程。
- Alembic 管理数据库迁移。
- 测试覆盖 QA 返工目标和报告导出等关键逻辑。

建议答辩表达：

> 项目不是脚本式 Demo，而是按前后端工程组织。数据库结构变更通过 Alembic 管理，关键返工逻辑有自动化测试，README 和答辩说明文档也同步维护。

### 11.5 合规、材料与答辩（10%）

系统对应点：

- 默认采集公开网页资料。
- Evidence 保留 source_url，方便确认来源。
- 系统面向公开竞品资料分析，不要求采集个人隐私数据。
- 可在答辩时说明后续会加入 robots.txt、来源白名单、敏感信息脱敏和采集频率控制。
- 提供本说明文档、README、代码库和可运行 Demo。

建议答辩表达：

> 当前 Demo 只使用公开网页信息，并保留来源 URL。对于问卷、访谈等可能包含个人信息的数据，系统设计上可以在 SourceDocument 入库前加入脱敏处理，并限制采集来源和访问频率。

---

## 12. 现场演示建议

### 12.1 演示路线

建议按以下顺序演示：

1. 打开登录页，使用 `Admin / Admin` 登录，或切换到注册模式演示用户名唯一校验。
2. 展示顶部当前用户和修改密码入口，说明用户名不可修改。
3. 进入“用户管理”页，展示管理员可查看用户、启用或停用普通账户。
4. 进入“历史记录”页，展示管理员可查看全部用户任务，并可按用户筛选。
5. 打开创建任务页。
6. 输入 AI 编程助手竞品分析 Demo。
7. 点击“解析需求”。
8. 展示 TaskPlan：主题、行业、竞品、分析维度。
9. 创建任务。
10. 进入任务详情页，展示 DAG：
   - Planner。
   - Dimension Prompt Planner。
   - Collector。
   - Evidence Extractor。
   - 多个动态维度 Agent。
   - Report Writer。
   - QA。
   - Report Finalizer。
11. 在任务详情页演示暂停、恢复或重启任务。
12. 打开某个维度 Agent，展示输入摘要、输出摘要、日志。
13. 打开 Evidence 页面，展示证据片段和 URL。
14. 打开 Claim 列表，展示 Claim 与 evidence ids。
15. 打开报告页，展示执行摘要、维度正文、总体结论。
16. 展示 QA 问题表和报告总结 Agent QA 问题表。
17. 展示导出 Markdown / PDF。
18. 如果有返工记录，展示 QA 失败维度和返工高亮。

### 12.2 演示重点

不要只展示最终报告。评委更关心“这是不是一个 Agent 协作系统”。因此要重点展示：

- DAG 图。
- 动态维度 Agent。
- Agent 日志。
- Evidence 和 Claim 绑定。
- QA 失败维度。
- 返工路径。
- 报告段落的 claim_ids / evidence_ids。

### 12.3 建议讲解节奏

可以按 5 分钟准备：

1. 30 秒：说明课题痛点和系统定位。
2. 30 秒：展示登录、注册、管理员用户管理和任务隔离。
3. 60 秒：展示一句话输入和 TaskPlan。
4. 90 秒：展示 DAG 和多 Agent 分工。
5. 60 秒：展示 Evidence / Claim / Report 的溯源链。
6. 60 秒：展示 QA 和返工闭环。
7. 30 秒：总结评分标准对应点和后续扩展。

---

## 13. 答辩常见问题与建议回答

### Q1：这和直接让大模型写一篇竞品报告有什么区别？

建议回答：

> 直接生成报告是一次性文本输出，过程不可控、证据不可查。我们的系统把任务拆成多个 Agent：采集、证据抽取、分析、撰写、质检和总结。关键结论先以 Claim 结构化存储，并绑定 Evidence。报告段落只能引用已有 Claim，最后可以从段落追溯到 evidence chunk 和原始 URL。

### Q2：如何保证结论可信？

建议回答：

> 第一，Analysis Agent 生成 Claim 时必须引用 evidence_ids。第二，Report Writer 写段落时只能引用已有 claim_ids。第三，QA Agent 检查 Claim 是否缺证据、报告是否漏维度、置信度是否过低。第四，Report Finalizer 还有 grounding QA，防止执行摘要和总体结论引入 Claim 之外的新事实。

### Q3：如果 QA 发现问题，系统真的会返工吗？

建议回答：

> 会。QA issue 可以给出 recollect、reanalyze、rewrite 三种动作。recollect 会先补采资料和抽取新证据，然后重新分析；reanalyze 会重跑目标维度分析 Agent；rewrite 会重写报告。返工目标来自 QA 失败维度全集，避免只根据局部 issue action 推断导致漏掉失败维度。

### Q4：为什么要每个维度一个 Agent？

建议回答：

> 竞品分析天然是多维度任务。每个维度一个 Agent 可以让职责边界更清晰，也方便并行、评分和返工。例如价格策略失败时，只需要重跑价格策略维度，而不需要重新生成全部内容。这样更贴近真实数字调研小组中不同分析师的协作方式。

### Q5：你们的知识 Schema 是固定的吗？

建议回答：

> 不是固定的。系统会根据用户确认的分析维度生成动态 Schema 和维度 Agent。当前 Demo 是 AI 编程助手，因此有产品定位、核心功能、Agent 能力、IDE 集成等维度。换成其它行业时，可以生成新的维度字段、prompt spec、画像和矩阵。

### Q6：向量数据库在系统里起什么作用？

建议回答：

> Milvus 存的是 evidence chunk 的 embedding，用于分析 Agent 按竞品、维度和来源类型进行语义召回。MySQL 保存 evidence 原文和业务关系，Milvus 只负责快速召回。检索失败时系统会回退到 MySQL 的可靠性排序，保证稳定性。

### Q7：如何处理幻觉问题？

建议回答：

> 系统从多个层面抑制幻觉：分析 Agent 只能基于检索到的 evidence 输出 Claim；Claim 必须绑定 evidence_ids；报告段落只能引用已有 claim_ids；后端会过滤非法 claim id 并自动补齐 evidence_ids；QA 会检查缺证据、弱证据和 unsupported claim；最终总结也要经过 grounding QA。

### Q8：如果网页资料本身有误怎么办？

建议回答：

> 系统会保留 source_url、source_type 和 reliability_score。当前主要依赖公开资料和来源类型进行初步可信度控制。后续可以扩展来源权重、发布时间检查、跨来源一致性校验和人工确认机制。

### Q9：为什么没有完全使用 LangGraph / CrewAI？

建议回答：

> 当前实现采用自研轻量 DAG runner，原因是比赛周期短，系统需要更强的数据库状态控制、前端可视化和返工调度可控性。我们的 Agent 节点、State、边和返工循环已经按 DAG 拆好，具备 LangGraph 迁移基础。答辩中我们重点展示的是 DAG 流转、结构化通信和真实闭环，而不是某个框架的名义接入。

### Q10：系统的合规策略是什么？

建议回答：

> 当前 Demo 使用公开网页资料，系统记录来源 URL，便于审查。对于未来接入问卷、访谈等数据，可以在入库前加入脱敏模块，移除手机号、邮箱、姓名等敏感信息，并增加来源白名单、robots.txt 检查和采集频率限制。

### Q11：多用户情况下如何保证任务不串号？

建议回答：

> 后端所有任务相关接口都会从 token 中解析当前用户，并按 `analysis_task.user_id` 做可见性校验。普通用户只能看到自己的历史、详情、证据、报告和 QA。管理员是特殊运维角色，可以查看全部用户任务，并对异常任务执行暂停、恢复或重启。这样既满足多人使用时的数据隔离，也保留了管理员处理队列和账户问题的能力。

---

## 14. 当前系统优势与边界

### 14.1 优势

- 端到端链路完整，可以现场 Demo。
- 多 Agent 分工清晰。
- 动态维度 Agent 贴合通用竞品分析。
- Evidence / Claim / Report 溯源链完整。
- QA 返工闭环真实可触发。
- QA 状态持久化，避免返工漏检。
- 前端展示 DAG、日志、QA、报告和导出。
- 工程结构完整，有数据库迁移和测试。

### 14.2 当前边界

- Firecrawl、LLM、Embedding、Milvus、Redis、MySQL 等外部服务可用性会影响完整流程。
- 自动竞品发现和维度推荐依赖 LLM 质量，需要人工确认。
- 公开网页资料质量不稳定，可能存在过时或不完整信息。
- 当前合规策略主要基于公开信息采集，robots.txt 和数据脱敏可继续增强。
- 当前 DAG runner 是自研实现，若评委强关注 LangGraph / CrewAI，需要解释取舍和迁移路径。

### 14.3 后续优化方向

- 引入来源可信度模型：官网、文档、价格页、第三方媒体、用户评论分别加权。
- 增加时间新鲜度检查：标记过期价格、旧版本功能和历史新闻。
- 增加跨来源一致性校验：同一 Claim 至少两个来源支持时提高 confidence。
- 增加人工修正入口：允许用户修改 Claim、标记证据无效、手动补充资料。
- 增加合规采集策略：robots.txt、频率限制、敏感信息脱敏。
- 将现有 workflow 节点迁移到 LangGraph，增强标准框架展示。
- 增加 Agent token 成本统计和 prompt 全量回放。

---

## 15. 答辩总结稿

可以用下面这段作为答辩收尾：

> 我们的系统面向企业产品团队的真实竞品分析流程，把传统人工调研中的信息采集、证据整理、维度分析、报告撰写和质量复核拆成多个专职 Agent。系统不是一次性生成报告，而是通过 DAG 组织 Agent 协作，通过 MySQL 和 Milvus 保存证据与结构化结论，通过 Claim-Evidence 绑定保证报告可溯源，通过 QA Agent 和 Report Finalizer QA 实现真实反馈闭环。  
>
> 对比赛评分标准而言，本系统重点覆盖了多 Agent 协作、结构化 Schema、DAG 可观测、结论溯源、自动返工、端到端工程和前端展示。当前 Demo 聚焦 AI 编程助手竞品分析，但底层设计是通用的，换行业时只需要调整竞品和分析维度，系统会动态生成维度 Agent、画像、矩阵和报告。
