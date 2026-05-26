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
- 证据抽取 Agent 支持并行 embedding + Milvus upsert worker。
- DAG 页面可视化展示并行采集 worker 和并行证据 worker。
- Analyst Agent 改为 Milvus RAG 检索，不再只按竞品从 MySQL 全量读取 evidence。
- ReportWriter 输出结构化 `report_json.sections`，报告段落可展开 Claim 和 Evidence。
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

前端会把四个 Analyst 显示为并行分支。当前后端中四个 Analyst 仍按顺序执行，但每个 Analyst 已经使用 Milvus RAG 检索证据。

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

重要修复：

- 以前 LLM 解析失败会 fallback 到 AI 编程助手 demo 数据。
- 现在 fallback 会根据用户输入推断目标产品和行业，不再硬编码 Cursor / Copilot / Windsurf / Tabnine。
- 如果用户只给目标产品和行业，不给竞品，则 `auto_discover_competitors=true`，collector 会自动搜索竞品。

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
4. 先创建 `evidence_chunk` 行。
5. 并发调用 embedding。
6. 并发写入 Milvus。
7. 主线程更新 `evidence_chunk.milvus_vector_id`。

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
| `status` | 任务状态 |
| `report_depth` | 报告深度 |
| `output_language` | 输出语言 |
| `task_plan_json` | TaskPlan JSON |
| `error_message` | 错误信息 |
| `created_at / updated_at` | 时间戳 |

### `agent_node`

持久化 Agent 节点。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `node_key` | 节点 key |
| `node_name` | 节点名 |
| `node_type` | 节点类型 |
| `status` | `pending / running / success / failed` |
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
| `POST` | `/api/v1/task-plans/parse` | 解析自然语言需求 |
| `GET` | `/api/v1/analysis-tasks` | 历史任务 |
| `POST` | `/api/v1/analysis-tasks` | 创建任务 |
| `GET` | `/api/v1/analysis-tasks/{task_id}` | 任务详情 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/nodes` | DAG 节点和边，包含虚拟并行 worker |
| `GET` | `/api/v1/analysis-tasks/{task_id}/logs` | Agent 日志 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/evidence` | Evidence Chunk |
| `GET` | `/api/v1/analysis-tasks/{task_id}/claims` | Claim |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report` | 报告、Claim、Evidence、QA payload |
| `GET` | `/api/v1/analysis-tasks/{task_id}/qa` | QA 结果 |

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
```

并发配置建议：

- `COLLECTOR_MAX_WORKERS=2~4`：Firecrawl 慢或限流时调小。
- `EVIDENCE_EXTRACTOR_MAX_WORKERS=4~8`：embedding 服务稳定时可调大。
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
6. 进入任务详情页，观察：
   - 主 DAG。
   - 并行采集 worker。
   - 并行证据 worker。
   - 四个 Analyst 分支。
   - QA 回流边。
   - Agent 日志。
7. 进入证据链页查看网页来源。
8. 进入报告页展开段落依据，查看 Claim 和 Evidence。
9. 进入历史记录页查看以前的任务。

## 当前已验证

今晚代码层面已做过：

```powershell
python -m compileall app
npm run build
```

前端构建会出现 Element Plus / Rolldown 的 pure annotation warning 和 chunk size warning，目前不影响运行。

## 当前能力边界

当前系统已经是可运行 MVP+，但仍有一些边界：

- 四个 Analyst 后端仍是顺序执行，前端展示为逻辑并行分支。
- Collector 和 Evidence Extractor 已经做了并发 worker。
- 并行 worker 是虚拟可视化节点，不是独立 Celery task。
- QA 返工最多 1 轮，避免无限循环。
- 任务恢复和幂等能力仍偏 MVP，生产环境还需要加强。
- Firecrawl、DeepSeek、DashScope、Milvus 任一外部服务不稳定都会影响任务耗时。
- ReportWriter 的结构化 JSON 依赖 LLM 输出质量，已有 fallback，但报告质量仍可进一步增强。
- Milvus RAG 检索已接入，但 query 策略还比较固定，可继续优化。

## 下一步可讨论方向

建议后续优先级：

1. 将四个 Analyst 改为真正并行执行，并保持 DB Session 隔离。
2. 将 collector/evidence worker 从线程池升级为可观测的 Celery 子任务。
3. 增加任务取消、暂停、重试能力。
4. 增加每个 worker 的真实进度，而不是只跟随父节点状态。
5. 增加 Firecrawl / LLM / Embedding / Milvus 的限流和重试策略。
6. 增加死信队列和失败任务恢复。
7. 优化 RAG query，根据用户选择的维度动态生成检索 query。
8. 增加 Evidence 去重、来源权重、时间新鲜度评分。
9. 增加更严格的 Claim schema 和报告评分 rubric。
10. 增加导出能力：Markdown、PDF、Word、HTML。
11. 增加多任务并发队列和任务优先级。
12. 增加评测集，用固定需求自动评估报告质量和证据命中率。

## 给 ChatGPT 的讨论摘要

如果要和 ChatGPT 继续讨论，可以直接复制下面这段：

```text
我现在有一个 FastAPI + Vue + Redis/Celery + MySQL + Milvus + Firecrawl + LLM 的竞品分析 Agent 系统。

当前主链路：
1. Planner 解析用户需求为 TaskPlan，支持自动发现竞品。
2. Collector 用 Firecrawl 搜索和抓取网页，已支持并行 search/scrape worker。
3. Evidence Extractor 清洗网页、切 chunk、embedding、写 MySQL 和 Milvus，已支持并行 embedding/Milvus worker。
4. 四个 Analyst：feature/pricing/market/security，使用 Milvus RAG 检索 evidence，再生成 Claim。
5. ReportWriter 基于 Claim 生成结构化 report_json.sections 和 Markdown。
6. 报告页可以展开每个段落对应的 Claim 和 Evidence。
7. QA Agent 做规则检查和 LLM 复核，结果包含 issues、next_action、target_nodes、revision_round。
8. QA 不通过时最多返工 1 轮，可回流 collector、analyst 或 report_writer。
9. 前端 VueFlow 展示 DAG、并行 worker、四个 Analyst 分支和 QA 回流边。
10. MySQL 保存业务数据，Milvus 保存向量，Redis 只做 Celery Broker 和 Worker 心跳。

当前问题和下一步：
- 四个 Analyst 现在后端仍是顺序执行，想改成真正并行。
- collector/evidence worker 现在是线程池和虚拟可视化节点，不是独立 Celery 子任务。
- 需要设计更可靠的任务取消、重试、恢复、限流和监控机制。
- 需要进一步优化 RAG query、Evidence 去重、来源权重、报告质量评分和导出能力。

请基于这个系统现状，帮我规划下一阶段最值得做的技术改进路线。
```
