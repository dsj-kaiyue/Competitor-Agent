# Competitive Agent

AI 驱动的通用竞品分析 Agent 协作系统。系统把用户的一句话竞品分析需求解析成结构化任务计划，然后通过多 Agent 协作完成资料采集、证据抽取、向量检索、结构化分析、报告生成、QA 复核和报告溯源。

这份 README 记录当前项目的真实状态，重点覆盖今晚完成的核心升级，适合拿去和 ChatGPT 继续讨论下一步行动方案。

## 当前版本状态

当前版本已经跑通真实主链路：

- Firecrawl：公开网页搜索和抓取。
- DeepSeek 兼容 OpenAI API：需求解析、Claim 生成、报告撰写、QA 复核。
- 阿里 DashScope `text-embedding-v4`：Evidence Chunk 向量化。
- Milvus：Evidence Chunk 向量存储与 RAG 检索。
- MySQL：任务、节点、日志、网页、证据、结论、报告、QA 结果的主存储。
- Redis + Celery：长任务异步执行。
- Vue 3 + VueFlow：前端展示任务 DAG、并行 worker、日志、证据链、报告和历史任务。

今晚新增或升级：

- 资料采集 Agent 支持并行 Firecrawl search/scrape worker。
- 证据抽取 Agent 支持批量 embedding、批量 Milvus insert 和并行 embedding worker。
- 证据抽取阶段会记录切块、MySQL、Embedding、Milvus 的阶段耗时。
- 四个 Analyst Agent 已改为后端真正并行执行，并且每个 Analyst 使用独立 DB Session。
- DAG 页面可视化展示并行采集 worker 和并行证据 worker。
- Analyst Agent 改为 Milvus RAG 检索，不再只按竞品从 MySQL 全量读取 evidence。
- ReportWriter 输出结构化 `report_json.sections`，报告段落可展开 Claim 和 Evidence。
- 报告页支持导出 Markdown 文件和 PDF 文件。
- 任务控制支持暂停、恢复、取消和手动重试；Celery 不再对业务失败自动反复 retry。
- 任务规划 Agent 在正式执行时只确认用户修改后的 TaskPlan，不再二次 LLM 解析覆盖前端修改。
- 创建页的竞品列表和分析维度支持添加、编辑和删除。
- 创建页解析需求时支持“自动发现竞品”开关；只要打开，不管用户是否已输入竞品，解析阶段都会补充竞品并立即回填到前端供用户增删。
- 数据库新写入时间统一使用北京时间。
- QA 结果扩展为带 `next_action / target_nodes / revision_round` 的结构化 payload。
- QA 不通过时最多返工 1 轮，可回流到 collector、analyst 或 report_writer。
- DAG 页面支持 QA 回流虚线边。
- 首页新增历史分析记录入口，历史页可查看以往任务、节点状态、报告和证据链。
- Planner 修复了 demo fallback 问题，不再把任意需求错误解析成 AI 编程工具竞品。

## 整体架构

```text
用户浏览器
  |
  | Vue 3 / Axios / VueFlow
  v
FastAPI API
  |
  | 创建任务、查询任务、DAG、日志、证据、报告
  v
MySQL  <---------------------------------------------+
  |                                                   |
  | 保存所有可审计业务数据                              |
  |                                                   |
Redis Broker / Worker Heartbeat                      |
  |                                                   |
  v                                                   |
Celery Worker                                        |
  |                                                   |
  | 执行多 Agent DAG                                  |
  v                                                   |
Firecrawl -> SourceDocument -> EvidenceChunk -> Milvus
                         |             ^
                         |             |
                         +--> Analyst RAG
                                  |
                                  v
                          Claim -> Report -> QA
```

核心设计原则：

- HTTP 请求只创建任务和查询状态，不阻塞等待完整分析。
- Celery Worker 执行真实长任务。
- MySQL 是最终业务数据来源。
- Redis 只做队列和运行态心跳。
- Milvus 只做向量检索，Evidence 原文仍以 MySQL 为准。
- 前端通过轮询任务、节点和日志接口展示动态执行过程。
- 数据库新写入时间统一使用北京时间，历史 UTC 数据不会自动回写。
- 项目功能变更需要同步更新 README，保证文档和真实系统行为一致。

## 技术框架

### 后端

- FastAPI：REST API。
- Pydantic / pydantic-settings：Schema 和环境变量配置。
- SQLAlchemy：ORM。
- PyMySQL：MySQL 驱动。
- Alembic：数据库迁移。
- Celery：异步任务执行。
- Redis：Celery Broker、Worker 心跳和队列恢复。
- pymilvus：Milvus 写入和检索。
- OpenAI 兼容 SDK：DeepSeek Chat 模型与 DashScope embedding 模型调用。
- Firecrawl SDK：网页搜索与抓取。
- markdown + reportlab：报告 Markdown 渲染与 PDF 文件导出。

### 前端

- Vue 3 + TypeScript。
- Vite。
- Element Plus。
- VueFlow。
- Axios。
- markdown-it。

### 基础设施

- MySQL：主业务库。
- Redis：消息队列。
- Milvus：向量库。
- Firecrawl：公开网页采集。
- DeepSeek：LLM。
- DashScope：Embedding。

## DeepSeek 调用链、请求体与返回取值

当前系统所有 DeepSeek Chat 请求都统一经过：

```text
backend/app/tools/llm_client.py
```

核心代码：

```python
model = ChatOpenAI(
    model=model_name,
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=90,
    temperature=0.2,
)

messages = []
if system:
    messages.append(("system", system))
messages.append(("human", prompt))

return str(model.invoke(messages).content)
```

### 请求地址

`.env` 中配置：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
```

因为使用的是 OpenAI 兼容 Chat Completions 协议，所以实际请求地址等价于：

```http
POST https://api.deepseek.com/v1/chat/completions
```

### 统一请求体结构

代码没有手写 HTTP body，而是由 `langchain_openai.ChatOpenAI` 生成。等价请求体如下：

```json
{
  "model": "deepseek-v4-pro",
  "temperature": 0.2,
  "messages": [
    {
      "role": "system",
      "content": "系统提示词"
    },
    {
      "role": "user",
      "content": "用户提示词"
    }
  ]
}
```

`timeout=90` 是客户端超时配置，不是请求体字段。

### 返回取值与思考内容

DeepSeek 思考模式会把思考内容放在：

```text
response.choices[0].message.reasoning_content
```

当前系统不会读取这个字段。系统只通过 LangChain 取：

```python
model.invoke(messages).content
```

等价于只使用：

```text
response.choices[0].message.content
```

因此当前系统不会保存、解析或使用 DeepSeek 的思考内容。后续 JSON 解析也只针对 `content` 字段中的最终回答。

### JSON 解析方式

多数 Agent 都要求 DeepSeek 只输出 JSON。后端统一用 `_json_from_text()` 解析：

```text
1. 如果 content 中有 ```json fenced block，先取 fenced block 内文本。
2. 优先直接 json.loads(content)。
3. 如果直接解析失败，再用正则从 content 中提取最外层 JSON 对象。
```

因此，后端使用的是最终回答里的 JSON，不使用 `reasoning_content`。

### 1. 需求解析 Planner Agent

触发时机：

```text
前端点击“解析需求”
POST /api/v1/task-plans/parse
```

代码位置：

```text
backend/app/agents/planner_agent.py
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
你是竞品分析 Planner Agent。请把用户输入解析成通用竞品分析 TaskPlan。

用户输入：
{user_input}

只输出 JSON，不要输出解释。格式：
{
  "topic": "string",
  "industry": "string or null",
  "target_product": null,
  "competitors": ["string"],
  "analysis_dimensions": ["string"],
  "report_depth": "simple|standard|deep",
  "output_language": "zh-CN",
  "auto_discover_competitors": true,
  "data_sources": ["official_website","pricing_page","docs","blog","news","reviews"]
}

规则：
- 如果用户只给了目标产品和行业，没有明确列出竞品，competitors 输出空数组，并把 auto_discover_competitors 设为 true。
- 不要使用示例产品或默认竞品填充结果。
- topic、industry、target_product 必须忠实来自用户输入。
```

期望返回：

```json
{
  "topic": "Firecrawl 竞品分析",
  "industry": "AI 数据采集",
  "target_product": "Firecrawl",
  "competitors": [],
  "analysis_dimensions": ["产品定位", "核心功能", "价格策略", "安全合规"],
  "report_depth": "standard",
  "output_language": "zh-CN",
  "auto_discover_competitors": true,
  "data_sources": ["official_website", "pricing_page", "docs", "blog", "news", "reviews"]
}
```

系统取出的数据：

```text
content -> JSON -> TaskPlan
```

然后写入或返回：

```text
topic
industry
target_product
competitors
analysis_dimensions
report_depth
output_language
auto_discover_competitors
data_sources
```

注意：

- 如果 DeepSeek 解析失败，会进入本地 fallback `_infer_task_plan()`。
- 解析接口请求体包含 `auto_discover_competitors`。
- 如果 `auto_discover_competitors=true`，后端会在 Planner 解析后继续执行竞品发现，不管 Planner 是否已经解析出竞品。
- 自动发现出的竞品会与 Planner 返回的 `competitors` 合并去重，再立刻返回前端展示。
- 如果用户在高级配置中重新打开自动发现，前端会再次调用解析接口并只合并新竞品，不覆盖其它已编辑配置。
- 用户可以在前端继续增加或删除竞品，正式分析只使用用户最终确认的列表。
- 点击“开始分析”后的 `planner` 节点不再二次调用 LLM，只确认前端最终 TaskPlan。

### 2. Collector 自动发现竞品

触发时机：

```text
解析需求阶段：
POST /api/v1/task-plans/parse
且请求体 auto_discover_competitors=true

正式分析阶段：
仅作为兜底逻辑，当 TaskPlan.auto_discover_competitors=true 且 competitors 仍为空时触发
```

代码位置：

```text
backend/app/graph/workflow.py
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请从搜索结果中识别与目标产品最相关的直接竞品或替代产品。
目标产品：{plan.target_product or plan.topic}
行业：{plan.industry}
搜索结果：
{discovery_context}

只输出 JSON 数组，最多 6 个产品名。不要包含目标产品本身，不要输出解释。
```

其中 `discovery_context` 来自 Firecrawl search，形如：

```text
- title=...; url=...; description=...
- title=...; url=...; description=...
```

期望返回：

```json
["Apify", "Bright Data", "Diffbot", "Browse AI"]
```

兼容返回：

```json
{
  "competitors": ["Apify", "Bright Data", "Diffbot", "Browse AI"]
}
```

系统取出的数据：

```text
content -> JSON
```

如果是数组，直接作为 `plan.competitors`；如果是对象，取：

```text
competitors
```

然后过滤空值和目标产品自身，最多保留 6 个竞品。

合并策略：

```text
1. 保留 Planner 或用户输入中已有的 competitors。
2. 自动发现结果按名称去重。
3. 不加入目标产品自身。
4. 将新增竞品追加到 competitors 后面。
5. 返回前端后由用户最终增删确认。
```

### 3. 四个 Analyst Agent

触发时机：

```text
evidence_extractor 完成后
```

四个 Analyst 当前后端真正并行执行：

```text
feature_analysis
pricing_analysis
market_analysis
security_analysis
```

代码位置：

```text
backend/app/graph/workflow.py
```

System prompt：

```text
你只输出合法 JSON，不编造证据。
```

User prompt 模板：

```text
你是严谨的竞品分析 Agent。请只基于给定 evidence 生成 {dimension} 维度的结构化结论。
竞品：{competitor}
分析主题：{plan.topic}
证据：
{_evidence_context(evidence, limit=12)}

输出 JSON 数组，最多 3 条。每条格式：
{"claim_text":"中文结论，必须具体且可被证据支撑","evidence_ids":[数字ID],"confidence":0.0到1.0,"risk_level":"low|medium|high"}
不要输出 JSON 之外的内容。
```

`dimension` 按 Agent 不同而不同：

```text
feature_analysis: 产品定位、核心功能、Agent 能力、IDE 集成
pricing_analysis: 价格策略、套餐结构、个人与团队商业化
market_analysis: 适用用户、市场定位、企业能力
security_analysis: 安全合规、隐私、企业治理能力
```

`_evidence_context()` 会把 RAG 检索到的 evidence 拼进 prompt，格式大致为：

```text
[evidence_id=101] title=...; url=...; source_type=...
证据正文片段...
```

期望返回：

```json
[
  {
    "claim_text": "Apify 更偏向通用 Web 自动化和数据采集平台，提供面向开发者的 Actor 生态。",
    "evidence_ids": [101, 104],
    "confidence": 0.86,
    "risk_level": "low"
  },
  {
    "claim_text": "其价格策略通常围绕平台用量和执行资源展开，团队使用场景需要结合套餐限制评估。",
    "evidence_ids": [109],
    "confidence": 0.74,
    "risk_level": "medium"
  }
]
```

系统取出的数据：

```text
content -> JSON array
```

每条数据取：

```text
claim_text
evidence_ids
confidence
risk_level
```

写入：

```text
claim.claim_text
claim.claim_type
claim.competitor_name
claim.confidence
claim.risk_level
claim_evidence.claim_id
claim_evidence.evidence_chunk_id
```

约束：

- `evidence_ids` 只允许引用本次传给 LLM 的 evidence。
- 如果 LLM 没返回有效 `evidence_ids`，但本次 RAG 有 evidence，系统默认绑定第一条 evidence。
- 每个竞品每个 Analyst 最多取 3 条 Claim。

### 4. ReportWriter Agent

触发时机：

```text
四个 Analyst 全部完成后
```

代码位置：

```text
backend/app/graph/workflow.py
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请基于以下结构化 Claim 生成中文竞品分析报告 JSON。
主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
分析维度：{', '.join(plan.analysis_dimensions)}
返工要求：{revision_instruction}

要求：
1. 只输出合法 JSON，不要 Markdown。
2. 每个 section 至少包含 section_id、title、paragraphs。
3. 每个关键 paragraph 必须包含 paragraph_id、text、claim_ids。
4. claim_ids 只能引用下方已有 claim_id，不要编造。
5. 不要输出 evidence_ids，后端会自动补齐。
6. 必须覆盖所有分析维度。

JSON 格式：
{"title":"...","sections":[{"section_id":"executive_summary","title":"执行摘要","paragraphs":[{"paragraph_id":"executive_summary_p1","text":"...","claim_ids":[1,2]}]}]}

Claims:
{claim_context}
```

`claim_context` 形如：

```text
[claim_id=1] competitor=Apify; type=feature; evidence_ids=[101, 102]; text=...
[claim_id=2] competitor=Bright Data; type=pricing; evidence_ids=[120]; text=...
```

期望返回：

```json
{
  "title": "Firecrawl 在 AI 数据采集领域的竞品分析报告",
  "sections": [
    {
      "section_id": "executive_summary",
      "title": "执行摘要",
      "paragraphs": [
        {
          "paragraph_id": "executive_summary_p1",
          "text": "Firecrawl 的主要竞品覆盖通用网页采集、企业数据平台和开发者自动化工具三类。",
          "claim_ids": [1, 3, 7]
        }
      ]
    }
  ]
}
```

系统取出的数据：

```text
content -> JSON object
```

重点字段：

```text
title
sections
sections[].section_id
sections[].title
sections[].paragraphs
paragraphs[].paragraph_id
paragraphs[].text
paragraphs[].claim_ids
```

后端会自动补充：

```text
paragraphs[].evidence_ids
report_json.mode = "firecrawl_llm_milvus_rag"
```

然后生成并保存：

```text
report.title
report.report_json
report.content_markdown
report.content_html
```

如果 DeepSeek 返回 JSON 不合法或缺少 `sections`，后端会使用 `_fallback_report_json()` 基于 Claim 生成基础报告。

### 5. QA Agent

触发时机：

```text
ReportWriter 完成后
```

代码位置：

```text
backend/app/graph/workflow.py
```

QA 先做本地规则检查，再把报告和规则问题交给 DeepSeek 复核。

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请复核这份竞品分析报告是否存在明显逻辑或证据问题。
仅基于报告和问题列表输出 JSON：
{"passed":true/false,"score":0.0到1.0,"issues":[{"type":"logic_gap|unsupported_claim|weak_evidence|schema_incomplete|writing_issue","severity":"low|medium|high","message":"中文问题","related_claim_id":null,"related_dimension":"feature|pricing|market|security","suggested_action":"recollect|reanalyze|rewrite|ignore"}]}

报告：
{report.content_markdown[:6000]}

规则检查问题：
{json.dumps(issues, ensure_ascii=False)}
```

期望返回：

```json
{
  "passed": false,
  "score": 0.72,
  "issues": [
    {
      "type": "weak_evidence",
      "severity": "medium",
      "message": "价格结论缺少官方价格页证据，建议补采价格页后重跑价格分析。",
      "related_claim_id": 12,
      "related_dimension": "pricing",
      "suggested_action": "recollect"
    }
  ]
}
```

系统取出的数据：

```text
content -> JSON object
```

重点字段：

```text
passed
score
issues
```

随后系统会把本地规则问题和 LLM 返回问题合并，生成：

```text
qa_result.passed
qa_result.score
qa_result.issues_json
```

`issues_json` 中还会补充工作流控制字段：

```json
{
  "passed": false,
  "score": 0.72,
  "issues": [],
  "next_action": "recollect",
  "target_nodes": ["collector"],
  "revision_reason": "...",
  "followup_queries": ["Example pricing plans official"],
  "revision_round": 0
}
```

### 不调用 DeepSeek 的 Agent 或步骤

以下步骤不向 DeepSeek Chat API 发送请求：

- 正式执行中的 `planner` 节点：只确认前端已编辑 TaskPlan。
- `collector` 的 Firecrawl search/scrape：调用 Firecrawl，不调用 DeepSeek；只有自动发现竞品时会调用 DeepSeek。
- `evidence_extractor`：调用 DashScope embedding 和 Milvus，不调用 DeepSeek Chat。
- `EvidenceRetriever.search()`：调用 DashScope embedding 生成 query vector，再查 Milvus，不调用 DeepSeek Chat。

DashScope embedding 请求地址来自：

```env
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
```

实际等价于：

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
```

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/                 # Planner Agent
│   │   ├── api/v1/                 # FastAPI API
│   │   ├── core/                   # config / database / celery / redis runtime / logging
│   │   ├── graph/                  # 多 Agent workflow
│   │   ├── models/                 # SQLAlchemy 模型
│   │   ├── schemas/                # Pydantic Schema
│   │   ├── services/               # task / log / evidence / RAG retriever / report / QA 服务
│   │   └── tools/                  # Firecrawl / LLM / Milvus 工具封装
│   ├── alembic/
│   ├── requirements.txt
│   └── .env                        # 本地配置，不提交
├── frontend/
│   ├── src/
│   │   ├── api/                    # API 封装
│   │   ├── components/             # DAG、QA、Claim、Evidence、Markdown 组件
│   │   ├── router/
│   │   ├── types/
│   │   └── views/                  # 创建页、详情页、历史页、报告页、证据页
│   └── package.json
└── document/
    └── tonight_core_improvements_for_codex.md
```

## Agent 与 DAG 设计

系统会为每个分析任务创建 9 个持久化 Agent 节点，定义在 `backend/app/services/task_service.py`，执行逻辑在 `backend/app/graph/workflow.py`。

| node_key | Agent | 职责 | 主要输出 |
| --- | --- | --- | --- |
| `planner` | 任务规划 Agent | 将用户自然语言解析为 TaskPlan；必要时自动发现竞品 | `task_plan_json` |
| `collector` | 资料采集 Agent | 生成搜索 query，调用 Firecrawl search/scrape | `source_document` |
| `evidence_extractor` | 证据抽取 Agent | 清洗网页、切 chunk、embedding、写 Milvus | `evidence_chunk` |
| `feature_analysis` | 功能分析 Agent | 基于 RAG evidence 生成产品/功能 Claim | `claim` |
| `pricing_analysis` | 价格分析 Agent | 基于 RAG evidence 生成价格 Claim | `claim` |
| `market_analysis` | 市场分析 Agent | 基于 RAG evidence 生成市场 Claim | `claim` |
| `security_analysis` | 安全合规分析 Agent | 基于 RAG evidence 生成安全合规 Claim | `claim` |
| `report_writer` | 报告撰写 Agent | 基于 Claim 生成结构化报告 JSON 和 Markdown | `report` |
| `qa` | QA Agent | 规则检查 + LLM 复核，必要时触发一次返工 | `qa_result` |

### 逻辑 DAG

```text
planner
  |
collector
  |
evidence_extractor
  |---------------- feature_analysis
  |---------------- pricing_analysis
  |---------------- market_analysis
  |---------------- security_analysis
                           |
                    report_writer
                           |
                          qa
```

前端会把四个 Analyst 显示为并行分支；后端也会使用独立线程并行执行四个 Analyst。每个 Analyst 都会创建独立 SQLAlchemy Session、独立 EvidenceRetriever 和独立 LLMClient，避免跨线程共享 DB Session。

### 运行时并行 worker 可视化

今晚新增了两类虚拟 worker：

```text
collector
  |-- collector_worker_1
  |-- collector_worker_2
  |-- collector_worker_3
  |-- collector_worker_4

evidence_extractor
  |-- evidence_worker_1
  |-- evidence_worker_2
  |-- evidence_worker_3
  |-- evidence_worker_4
```

这些 worker 是运行时可视化节点：

- 不写入 `agent_node` 表。
- 后端 `/analysis-tasks/{task_id}/nodes` 动态追加。
- 数量来自 `.env` 配置。
- 状态跟随父 Agent：父节点 `running` 时 worker 显示 `running`，父节点 `success` 时 worker 显示 `success`。
- 主要用于让用户看到资料采集和证据抽取确实是并行执行。

配置：

```env
COLLECTOR_MAX_WORKERS=4
EVIDENCE_EXTRACTOR_MAX_WORKERS=4
EVIDENCE_EMBEDDING_BATCH_SIZE=8
```

如果外部服务限流，可以调小；如果网络和 API 稳定，可以逐步调大。

## 当前数据流

### 1. 需求解析

前端调用：

```http
POST /api/v1/task-plans/parse
```

Planner Agent 输出 TaskPlan：

- `topic`
- `industry`
- `target_product`
- `competitors`
- `analysis_dimensions`
- `report_depth`
- `output_language`
- `auto_discover_competitors`
- `data_sources`

当前行为：

- 以前 LLM 解析失败会 fallback 到 AI 编程助手 demo 数据。
- 现在 fallback 会根据用户输入推断目标产品和行业，不再硬编码 Cursor / Copilot / Windsurf / Tabnine。
- 创建页有“自动发现竞品”开关，默认打开。
- 只要解析请求中的 `auto_discover_competitors=true`，后端就会额外执行竞品发现，并把发现结果追加到 `competitors` 返回前端；即使用户原始输入里已经写了竞品，也会继续补充。
- 如果用户关闭“自动发现竞品”，后端只做需求解析，不额外搜索补充竞品。
- 如果解析后在高级配置中把“自动发现竞品”从关闭切换为开启，前端会再次请求解析与自动发现，但只合并新增竞品，不覆盖用户已经编辑过的主题、维度、语言等其它 TaskPlan 字段。
- 前端会展示 TaskPlan，用户可以继续编辑竞品、分析维度、报告深度和输出语言。
- 竞品列表和分析维度都支持添加、编辑和删除。
- 点击“开始分析”后，workflow 中的 `planner` 节点只确认和落库最终 TaskPlan，不再重新调用 LLM 解析 `user_input`，因此不会覆盖用户在前端修改过的竞品或分析维度。

### 2. 创建任务

前端调用：

```http
POST /api/v1/analysis-tasks
```

后端创建：

- 1 条 `analysis_task`
- 9 条 `agent_node`

然后：

- 如果 Celery Worker 心跳存在，任务进入 Redis 队列 `competitor_agent_analysis`。
- 如果 Worker 不可用且 fallback 配置开启，后端会降级到本地后台线程。

### 3. 资料采集

Collector 对每个竞品生成 query：

```text
{competitor} {industry/topic} official product features
{competitor} pricing plans official
{competitor} docs enterprise security compliance privacy official
```

若 QA 返工要求补采，还会追加 QA 生成的 follow-up query。

今晚已改为并行：

1. 每个竞品内部并发执行多个 Firecrawl search。
2. URL 去重。
3. 每个竞品最多抓取 5 个 URL。
4. 并发 scrape URL。
5. 主线程统一写入 `source_document`。

这样避免跨线程共享 SQLAlchemy Session。

### 4. 证据抽取与向量化

Evidence Extractor 执行：

1. 读取 `source_document`。
2. 清洗 Markdown / HTML 文本。
3. 按约 1400 字符切片，overlap 约 180。
4. 批量创建 `evidence_chunk` 行。
5. 按 `EVIDENCE_EMBEDDING_BATCH_SIZE` 分批调用 embedding。
6. 使用 `EVIDENCE_EXTRACTOR_MAX_WORKERS` 并发处理 embedding batch。
7. 批量写入 Milvus，并在每批 insert 后 flush。
8. 批量更新 `evidence_chunk.milvus_vector_id`。
9. 记录切块、MySQL 创建、Embedding、Milvus 写入、MySQL 更新和总耗时。

DashScope `text-embedding-v4` 当前单次 embedding 请求最多 10 条 input，因此建议：

```env
EVIDENCE_EXTRACTOR_MAX_WORKERS=4
EVIDENCE_EMBEDDING_BATCH_SIZE=8
```

如果 batch embedding 失败，系统会自动降级：

1. 批量请求失败后拆成单条重试。
2. 单条仍失败的 chunk 保留在 MySQL。
3. 失败 chunk 的 `milvus_vector_id` 标记为 `embedding-failed-{chunk_id}`。
4. 少量 chunk embedding 失败不会直接让整个任务失败。
5. 后续 Analyst 如果 Milvus 没命中，会 fallback 到 MySQL evidence。

Milvus collection：

```text
evidence_chunks
```

Milvus 字段：

```text
id
task_id
chunk_id
competitor_name
source_type
source_url
embedding
```

线程中只调用外部 IO，不使用 DB Session。

### 5. Milvus RAG 检索

新增服务：

```text
backend/app/services/evidence_retriever.py
```

接口：

```python
EvidenceRetriever.search(
    task_id,
    query,
    competitor_name=None,
    source_type=None,
    top_k=8,
    node_id=None,
)
```

执行逻辑：

1. 用 embedding 模型生成 query vector。
2. 用 Milvus filter 限定 `task_id`。
3. 如果指定 `competitor_name`，继续过滤竞品。
4. 如果指定 `source_type`，继续过滤来源类型。
5. Milvus 返回 `chunk_id`。
6. 回 MySQL 查询 `evidence_chunk` 原文。
7. 按 Milvus score 顺序返回。
8. Milvus 异常时 fallback 到 MySQL。
9. 检索过程写入 `agent_run_log`。

日志 payload 示例：

```json
{
  "retrieval_mode": "milvus_rag",
  "query": "Cursor pricing plans subscription team enterprise billing official",
  "competitor_name": "Cursor",
  "top_k": 8,
  "retrieved_chunk_ids": [1, 2, 3],
  "fallback_used": false
}
```

fallback 示例：

```json
{
  "retrieval_mode": "mysql_fallback",
  "reason": "Milvus search failed: ...",
  "retrieved_chunk_ids": [1, 2, 3]
}
```

### 6. Claim 生成

四个 Analyst 分别构造不同 query：

| Agent | query 方向 | source_type 偏好 |
| --- | --- | --- |
| `feature_analysis` | product positioning, core features, topic, dimension | 无强制 |
| `pricing_analysis` | pricing, plans, subscription, team, enterprise, official | `pricing_page` |
| `market_analysis` | target users, market positioning, enterprise teams, strategy | 无强制 |
| `security_analysis` | security, privacy, compliance, data protection, training data policy | 无强制 |

执行方式：

- 四个 Analyst 在后端使用 `ThreadPoolExecutor` 真正并行执行。
- 每个 Analyst 线程独立创建 SQLAlchemy `SessionLocal()`。
- 每个 Analyst 独立创建 `EvidenceRetriever`、`LLMClient` 和 Milvus 查询上下文。
- 主线程只收集各 Analyst 生成的 claim id，并等待全部 Analyst 完成后再进入 `report_writer`。
- QA 返工时，如果目标是多个 Analyst，也会并行重跑目标 Analyst。

LLM 输出 Claim JSON：

```json
[
  {
    "claim_text": "中文结论",
    "evidence_ids": [101, 102],
    "confidence": 0.86,
    "risk_level": "low"
  }
]
```

如果 LLM 没返回 `evidence_ids`，系统默认绑定本次 RAG 检索的 top evidence。

Claim 只允许绑定本次传给 LLM 的 evidence，避免把全量 evidence 都挂上去。

### 7. 报告生成与段落溯源

ReportWriter 不再只让 LLM 输出 Markdown，而是要求 LLM 输出结构化 JSON：

```json
{
  "title": "竞品分析报告",
  "sections": [
    {
      "section_id": "executive_summary",
      "title": "执行摘要",
      "paragraphs": [
        {
          "paragraph_id": "executive_summary_p1",
          "text": "关键结论文本",
          "claim_ids": [101, 102],
          "evidence_ids": [201, 202]
        }
      ]
    }
  ],
  "mode": "firecrawl_llm_milvus_rag"
}
```

注意：

- LLM 只负责输出 `claim_ids`。
- 后端根据 `claim_evidence` 自动补齐 `evidence_ids`。
- Markdown 由 `report_json` 渲染生成。
- 如果 LLM 输出 JSON 失败，后端会 fallback 生成基础结构化报告。

前端报告页支持：

- 按 section / paragraph 展示报告。
- 每个段落显示“查看依据：N 条 Claim，M 条 Evidence”。
- 点击展开后显示相关 Claim、置信度、Evidence 来源 URL、source_type 和原文片段。

### 8. QA 反馈闭环

QA Agent 至少检查：

- 每个核心 Claim 是否绑定 Evidence。
- `pricing` Claim 是否优先有 `official_website` / `pricing_page` 来源。
- `security` Claim 是否优先有 `official_website` / `docs` / `security` / `enterprise` 来源。
- 报告是否覆盖用户选择的分析维度。
- Claim `confidence < 0.6` 是否标记 weak evidence。
- 报告是否为空、过短或缺少结构。

`qa_result.issues_json` 现在保存结构化 payload：

```json
{
  "passed": false,
  "score": 0.72,
  "issues": [
    {
      "type": "weak_evidence",
      "severity": "medium",
      "message": "价格 Claim 缺少官方价格页证据",
      "related_claim_id": 12,
      "related_competitor": "Example",
      "related_dimension": "pricing",
      "suggested_action": "recollect",
      "target_node": null,
      "search_query": "Example pricing plans official"
    }
  ],
  "next_action": "recollect",
  "target_nodes": ["collector"],
  "revision_reason": "价格 Claim 缺少官方价格页证据",
  "followup_queries": ["Example pricing plans official"],
  "revision_round": 0
}
```

返工规则：

- 最多返工 1 轮。
- `recollect`：回流到 collector，再 evidence_extractor，再目标 analyst，再 report_writer，再 qa。
- `reanalyze`：回流到目标 analyst，再 report_writer，再 qa。
- `rewrite`：回流到 report_writer，再 qa。
- 返工会追加日志，不删除第一次执行日志。
- 前端 DAG 会展示 `qa -> target_node` 的橙色虚线回流边。

## 前端页面

### 创建页

文件：

```text
frontend/src/views/TaskCreateView.vue
```

能力：

- 输入自然语言需求。
- 点击解析需求。
- 展示并可编辑 TaskPlan。
- 创建分析任务。
- 进入任务详情。
- 提供历史记录入口。

### 任务详情页

文件：

```text
frontend/src/views/TaskDetailView.vue
frontend/src/components/DagFlow.vue
```

能力：

- 展示任务状态。
- 展示 DAG。
- 展示并行 collector worker 和 evidence worker。
- 展示四个 Analyst 分支。
- 展示 QA 回流虚线边。
- 展示按 Agent 分组的日志。
- 日志按时间倒序显示，最新动态在上方。
- 同一 Agent 的日志可折叠。
- 跳转阶段耗时页面。

### 历史记录页

文件：

```text
frontend/src/views/HistoryView.vue
```

能力：

- 查看历史分析任务。
- 查看任务状态、节点状态统计。
- 跳转任务详情、报告、证据链。

### 证据链页

文件：

```text
frontend/src/views/EvidenceView.vue
```

能力：

- 查看 Evidence Chunk。
- 查看来源 URL、标题、source_type、竞品、可信度。

### 阶段耗时页

文件：

```text
frontend/src/views/TimingView.vue
```

能力：

- 查看 `log_type=metric` 的性能日志。
- 展示证据抽取阶段的文档数、chunk 数、embedding 批次数、并发 worker 数。
- 可视化展示文本切块、MySQL 创建 chunk、批量 embedding、Milvus 批量写入、MySQL 更新向量 ID 的耗时。
- QA 返工导致多次证据抽取时，可通过“证据抽取轮次”选择器查看每一轮。
- 显示 embedding 失败 chunk 数，辅助判断批量 embedding 是否触发限流或参数错误。
- 用于判断瓶颈在 DashScope embedding、Milvus、MySQL 还是本地切块。

### 报告页

文件：

```text
frontend/src/views/ReportView.vue
```

能力：

- 展示结构化报告。
- 按段落展开 Claim 和 Evidence。
- 展示 QA 结果。
- 展示结构化 Claim 列表。

## 数据库设计

### `analysis_task`

任务主表。

| 字段 | 含义 |
| --- | --- |
| `id` | 任务 ID |
| `user_input` | 用户原始需求 |
| `topic` | 主题 |
| `industry` | 行业 |
| `target_product` | 目标产品 |
| `status` | 任务状态，例如 `queued / running / paused / pause_requested / canceled / cancel_requested / success / failed` |
| `report_depth` | 报告深度 |
| `output_language` | 输出语言 |
| `task_plan_json` | TaskPlan JSON |
| `error_message` | 错误信息 |
| `created_at / updated_at` | 时间戳，新写入数据使用北京时间 |

### `agent_node`

持久化 Agent 节点。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `node_key` | 节点 key |
| `node_name` | 节点名 |
| `node_type` | 节点类型 |
| `status` | `pending / running / paused / canceled / success / failed` |
| `input_summary` | 输入摘要 |
| `output_summary` | 输出摘要 |
| `started_at / ended_at` | 开始和结束时间 |
| `duration_ms` | 耗时 |
| `retry_count` | 返工次数 |
| `error_message` | 错误 |

并行 worker 不写入该表，是 `/nodes` 接口动态生成的虚拟节点。

### `agent_run_log`

Agent 运行日志。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `node_id` | Agent 节点 ID |
| `log_type` | `info / warning / error` |
| `message` | 日志文本 |
| `payload_json` | 结构化 payload |
| `created_at` | 时间 |

`log_type` 目前包括：

- `info`：普通执行日志。
- `warning`：降级、跳过、弱错误等告警。
- `error`：节点失败或外部调用失败。
- `metric`：阶段耗时指标，目前主要用于证据抽取阶段。

### `source_document`

Firecrawl 抓取网页。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `competitor_name` | 竞品 |
| `source_url` | URL |
| `source_title` | 标题 |
| `source_type` | 来源类型 |
| `content_markdown` | Markdown |
| `content_text` | 清洗文本 |
| `metadata_json` | 搜索和抓取元数据 |

### `evidence_chunk`

证据切片。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `source_document_id` | 来源文档 |
| `competitor_name` | 竞品 |
| `source_url / source_title` | 来源信息 |
| `source_type` | 来源类型 |
| `chunk_index` | 切片序号 |
| `chunk_text` | 证据文本 |
| `reliability_score` | 可信度 |
| `milvus_vector_id` | Milvus 向量 ID |

### `claim`

结构化结论。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `agent_node_id` | 生成 Agent |
| `competitor_name` | 竞品 |
| `claim_type` | `feature / pricing / market / security` |
| `claim_text` | 结论 |
| `confidence` | 置信度 |
| `risk_level` | 风险等级 |

### `claim_evidence`

Claim 与 Evidence 多对多关联表。

| 字段 | 含义 |
| --- | --- |
| `claim_id` | Claim ID |
| `evidence_chunk_id` | Evidence Chunk ID |

### `report`

报告。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `title` | 标题 |
| `content_markdown` | Markdown |
| `content_html` | HTML |
| `report_json` | 结构化报告，包含 sections / paragraphs / claim_ids / evidence_ids |

### `qa_result`

QA 结果。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `report_id` | 报告 ID |
| `passed` | 是否通过 |
| `score` | 得分 |
| `issues_json` | QA payload，包含 issues / next_action / target_nodes / revision_round |

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/task-plans/parse` | 解析自然语言需求；请求体支持 `auto_discover_competitors`，打开后会补充竞品并立即返回前端 |
| `GET` | `/api/v1/analysis-tasks` | 历史任务 |
| `POST` | `/api/v1/analysis-tasks` | 创建任务 |
| `GET` | `/api/v1/analysis-tasks/{task_id}` | 任务详情 |
| `POST` | `/api/v1/analysis-tasks/{task_id}/pause` | 请求暂停任务，运行中任务会在最近的检查点停为 `paused` |
| `POST` | `/api/v1/analysis-tasks/{task_id}/resume` | 恢复已暂停任务，重新入队并跳过已成功节点 |
| `POST` | `/api/v1/analysis-tasks/{task_id}/cancel` | 请求取消任务，队列中任务直接取消，运行中任务在最近检查点取消 |
| `POST` | `/api/v1/analysis-tasks/{task_id}/retry` | 重试任务，清理旧采集数据、证据、结论、报告和 QA 后从头执行 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/nodes` | DAG 节点和边，包含虚拟并行 worker |
| `GET` | `/api/v1/analysis-tasks/{task_id}/logs` | Agent 日志 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/evidence` | Evidence Chunk |
| `GET` | `/api/v1/analysis-tasks/{task_id}/claims` | Claim |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report` | 报告、Claim、Evidence、QA payload |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report/export?format=markdown` | 导出 Markdown 报告文件 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report/export?format=pdf` | 导出 PDF 报告文件 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/qa` | QA 结果 |

任务控制说明：

- 暂停和取消是协作式控制，不会强杀正在进行中的 Firecrawl、LLM、Embedding 或 Milvus 调用。
- 后端会在每个 Agent 节点开始前，以及采集、证据抽取、分析循环中检查控制状态。
- 暂停后的任务状态为 `paused`，恢复时重新入队，已经 `success` 的节点会跳过，`paused` 节点会继续执行。
- 取消后的任务状态为 `canceled`，不会自动清理已经写入的中间数据。
- 重试会清理该任务旧的 `source_document / evidence_chunk / claim / claim_evidence / report / qa_result`，并将所有节点重置为 `pending` 后重新执行。
- Celery 任务的自动业务 retry 已关闭，失败后不会自己反复重跑；需要用户在前端手动点击“重试”。

## 配置

后端配置在：

```text
backend/.env
```

示例，不要把真实密钥提交到仓库：

```env
APP_ENV=dev
APP_NAME=competitive-agent-system

DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/competitor_agent?charset=utf8mb4

CELERY_BROKER_URL=redis://:password@host:6379/0
CELERY_RESULT_BACKEND=redis://:password@host:6379/1

FIRECRAWL_API_KEY=your_firecrawl_key

LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-v4-pro

EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=your_dashscope_key
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1536

MILVUS_URI=http://host:19530
MILVUS_TOKEN=your_milvus_token
MILVUS_COLLECTION=evidence_chunks

RUN_TASKS_INLINE=false
FALLBACK_TO_LOCAL_THREAD_ON_CELERY_ERROR=true
FALLBACK_TO_LOCAL_THREAD_WHEN_WORKER_UNAVAILABLE=true

CELERY_WORKER_HEARTBEAT_TTL_SECONDS=45
CELERY_WORKER_HEARTBEAT_INTERVAL_SECONDS=10
CELERY_VISIBILITY_TIMEOUT_SECONDS=120
CELERY_QUEUED_RECOVERY_MAX_AGE_SECONDS=1800

COLLECTOR_MAX_WORKERS=4
EVIDENCE_EXTRACTOR_MAX_WORKERS=4
EVIDENCE_EMBEDDING_BATCH_SIZE=8
```

并发配置建议：

- `COLLECTOR_MAX_WORKERS=2~4`：Firecrawl 慢或限流时调小。
- `EVIDENCE_EXTRACTOR_MAX_WORKERS=4~8`：embedding 服务稳定时可调大；并发过高会触发限流。
- `EVIDENCE_EMBEDDING_BATCH_SIZE=1~10`：DashScope `text-embedding-v4` 单次请求最多 10 条 input，建议 8。
- 并发越高，越可能触发 Firecrawl / embedding / Milvus 限流。

前端配置：

```text
frontend/.env.development
```

示例：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## 启动

### 1. 后端依赖

```powershell
conda create -n competitor-agent python=3.11
conda activate competitor-agent
cd D:\Code\Python\Competitor-Agent\backend
pip install -r requirements.txt
```

### 2. 前端依赖

```powershell
cd D:\Code\Python\Competitor-Agent\frontend
npm install
```

### 3. MySQL 初始化

```sql
CREATE DATABASE competitor_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

初始化表：

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -m app.db_init
```

或：

```powershell
alembic upgrade head
```

### 4. 启动 FastAPI

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

检查：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 5. 启动 Celery Worker

Windows 本地建议：

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -m celery -A app.worker:celery_app worker --loglevel=info --pool=solo -Q competitor_agent_analysis --without-gossip --without-mingle --without-heartbeat
```

说明：

- `--pool=solo` 适合 Windows。
- 不建议用 `conda run celery ...` 包装长进程。
- 如果正在跑任务，不要重启 Celery Worker，否则可能中断当前任务。
- 只重启 FastAPI 通常不会中断 Celery Worker 中正在执行的任务。

### 6. 启动前端

```powershell
cd D:\Code\Python\Competitor-Agent\frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173/
```

## Redis / Celery 运行说明

队列名：

```text
competitor_agent_analysis
```

Worker 心跳：

```text
competitor_agent:worker:heartbeat
```

Celery / Kombu 内部 key 可能包括：

```text
_kombu.binding.competitor_agent_analysis
competitor_agent_analysis
```

远程 Redis 建议：

```bash
redis-cli -h your-host -p 6379 -a 'password' CONFIG SET timeout 0
redis-cli -h your-host -p 6379 -a 'password' CONFIG SET tcp-keepalive 60
redis-cli -h your-host -p 6379 -a 'password' CONFIG REWRITE
```

含义：

- `timeout 0`：服务端不主动断开空闲客户端。
- `tcp-keepalive 60`：更快识别异常断开的连接。
- 本地停止 Celery Worker 时，连接会正常释放，不会永久占满。

## Milvus 查看

Evidence 向量是在 `evidence_extractor` 阶段写入 Milvus 的，不是在 Firecrawl 搜索阶段写入。

验证 collection：

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -c "from app.core.config import settings; from pymilvus import MilvusClient; c=MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token); print(c.list_collections()); print(c.get_collection_stats(settings.milvus_collection))"
```

如果 Milvus 内置页面看不到数据，不一定表示没写入。建议用 Attu 或 pymilvus 查询 collection 和 row count。

## 典型使用流程

1. 打开前端首页。
2. 输入需求，例如：

```text
请分析 Firecrawl 在 AI 数据采集领域的竞品情况，重点关注产品定位、核心功能、数据采集能力、价格策略、开发者生态、安全合规和适用用户。
```

3. 点击“解析需求”。
4. 检查 TaskPlan。
5. 点击“开始分析”。
   - 任务会使用前端最终确认的 TaskPlan，不会再二次规划覆盖你的修改。
6. 进入任务详情页，观察：
   - 主 DAG。
   - 并行采集 worker。
   - 并行证据 worker。
   - 四个 Analyst 分支。
   - QA 回流边。
   - Agent 日志。
7. 进入阶段耗时页查看证据抽取每轮耗时。
8. 进入证据链页查看网页来源。
9. 进入报告页展开段落依据，查看 Claim 和 Evidence。
10. 进入历史记录页查看以前的任务。

## 当前已验证

今晚代码层面已做过：

```powershell
python -m compileall app
npm run build
```

前端构建会出现 Element Plus / Rolldown 的 pure annotation warning 和 chunk size warning，目前不影响运行。

## 当前能力边界

当前系统已经是可运行 MVP+，但仍有一些边界：

- 四个 Analyst 后端已真正并行执行；后续仍可继续增加独立超时、限流和部分失败降级策略。
- Collector 和 Evidence Extractor 已经做了并发 worker。
- 并行 worker 是虚拟可视化节点，不是独立 Celery task。
- QA 返工最多 1 轮，避免无限循环。
- 任务恢复和幂等能力仍偏 MVP，生产环境还需要加强。
- Firecrawl、DeepSeek、DashScope、Milvus 任一外部服务不稳定都会影响任务耗时。
- ReportWriter 的结构化 JSON 依赖 LLM 输出质量，已有 fallback，但报告质量仍可进一步增强。
- Milvus RAG 检索已接入，但 query 策略还比较固定，可继续优化。

## 下一步可讨论方向

建议后续优先级：

1. 将 collector/evidence worker 从线程池升级为可观测的 Celery 子任务。
2. 为并行 Analyst 增加独立超时、限流和部分失败降级策略。
3. 增强任务控制的生产级能力，例如 Celery revoke、任务取消补偿清理、断点级恢复。
4. 增加每个 worker 的真实进度，而不是只跟随父节点状态。
5. 增加 Firecrawl / LLM / Embedding / Milvus 的限流和重试策略。
6. 增加死信队列和失败任务恢复。
7. 优化 RAG query，根据用户选择的维度动态生成检索 query。
8. 增加 Evidence 去重、来源权重、时间新鲜度评分。
9. 增加更严格的 Claim schema 和报告评分 rubric。
10. 扩展导出能力：Word、HTML、带证据附录的审计版 PDF。
11. 增加多任务并发队列和任务优先级。
12. 增加评测集，用固定需求自动评估报告质量和证据命中率。
