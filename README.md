# Competitive Agent

Competitive Agent 是一个 AI 驱动的通用竞品分析 Agent 协作系统。用户输入一句竞品分析需求后，系统会解析任务计划、自动发现竞品、生成动态分析维度，并通过多 Agent 协作完成资料采集、证据抽取、RAG 检索、结构化 Claim 生成、报告撰写、QA 复核、自动返工和报告导出。

系统面向需要可追溯竞品研究、产品调研、市场分析和技术选型评估的团队。它不是只生成一段总结文本，而是把分析过程拆成可观察、可返工、可审计的流水线。

## 功能特性

- 一句话需求解析：将自然语言需求解析为 `TaskPlan`，包含主题、行业、竞品、分析维度、报告深度和输出语言。
- 自动发现竞品：可根据目标产品和行业自动补充候选竞品。
- 自动补充分析维度：可根据业务场景推荐额外分析维度，用户仍可在前端确认、增删和编辑。
- 动态维度 Agent：每个分析维度都会创建一个独立的 `dimension_analysis_*` Agent，并行执行，只负责该维度的分析。
- 资料采集与证据抽取：基于 Firecrawl 采集网页内容，抽取 evidence chunk，并写入 MySQL 与 Milvus。
- RAG 支撑结论：动态维度 Agent 基于 Milvus 检索结果生成结构化 Claim，并保留 Claim 到 Evidence 的绑定。
- 动态画像和对比矩阵：根据用户确认的分析维度生成竞品画像和矩阵，不依赖固定行业字段。
- 报告生成与段落溯源：报告正文由 Claim 和 Evidence 支撑，可导出 Markdown 和 PDF。
- QA 自动复核与返工：QA Agent 对每个分析维度打分，自动决定补采、重分析或重写。
- 维度 Agent QA 状态：每个分析 Agent 的数据库记录保存当前 QA 状态，作为下一轮返工调度的权威来源。
- DAG 可视化：前端展示 Agent 执行图、并行 worker、节点状态、日志、耗时和返工高亮。
- 任务控制：支持暂停、恢复、取消、重试和历史任务查看。

## 系统架构

```text
Frontend (Vue 3)
  |
  | REST API
  v
FastAPI Backend
  |
  | enqueue / fallback local thread
  v
Celery Worker
  |
  v
Workflow Graph
  Planner
    -> Dimension Prompt Planner
    -> Collector
    -> Evidence Extractor
    -> Dynamic Dimension Analysts (parallel)
    -> Dynamic Profiles / Matrices
    -> Report Writer
    -> QA Agent
    -> optional revision loop
    -> Report Finalizer

Storage:
  MySQL  : tasks, agent nodes, logs, source documents, evidence, claims, reports, QA history
  Milvus : vector index for evidence chunks
  Redis  : Celery broker/result backend and worker heartbeat
```

## 技术栈

后端：

- Python 3.11
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Celery + Redis
- MySQL
- Milvus
- Firecrawl
- OpenAI-compatible LLM / Embedding API

前端：

- Vue 3
- TypeScript
- Vite
- Element Plus
- Vue Flow
- ECharts
- Pinia

## Agent 流程

| Agent | 职责 | 主要产物 |
| --- | --- | --- |
| Planner Agent | 确认最终任务计划 | `analysis_task.task_plan_json` |
| Dimension Suggestion Agent | 解析阶段补充分析维度 | 前端可编辑的 `analysis_dimensions` |
| Competitor Discovery Agent | 解析阶段发现竞品 | 前端可编辑的竞品列表 |
| Dimension Prompt Planner Agent | 为每个维度生成专属 prompt spec | `agent_node.input_summary` 和运行态 spec |
| Collector Agent | 按竞品和维度采集网页资料 | `source_document` |
| Evidence Extractor Agent | 抽取 evidence chunk 并向量化 | `evidence_chunk` 和 Milvus vectors |
| Dynamic Dimension Analyst Agent | 每个维度一个 Agent，并行生成 Claim | `claim` / `claim_evidence` |
| Report Writer Agent | 生成维度正文 section | `report` |
| QA Agent | 规则检查 + LLM 复核 + 返工决策 | `qa_result` 和 `agent_node` QA 状态 |
| Report Finalizer Agent | 生成执行摘要、总体结论、建议和风险提示 | 最终 `report` |

## QA 与返工机制

QA Agent 会对本轮检查范围内的每个动态维度输出 `dimension_scores`。系统同时维护两类 QA 数据：

- `qa_result`：保存每一轮 QA 的完整历史快照，包括 issues、分数、返工动作、目标节点和检查范围。
- `agent_node` 当前 QA 状态：保存每个维度 Agent 最新的 QA 判定，用于调度下一轮返工。

`agent_node` 中的 QA 状态字段：

| 字段 | 含义 |
| --- | --- |
| `qa_passed` | 当前维度是否通过 QA |
| `qa_score` | 当前维度最新 QA 分数 |
| `qa_revision_round` | 该状态来自第几轮 QA |
| `qa_issue_count` | 当前维度关联的问题数量 |
| `qa_updated_at` | QA 状态更新时间 |

返工规则：

- 第一轮全局 QA 会覆盖全部分析维度。
- 无问题维度写入 `qa_passed=true`。
- 有问题维度写入 `qa_passed=false`。
- 下一轮返工目标直接从数据库查询 `qa_passed=false` 的动态维度 Agent。
- `recollect` 会执行补采资料、证据抽取、目标维度重分析、局部报告重写和局部 QA。
- `reanalyze` 会只重跑目标维度分析、局部报告重写和局部 QA。
- `rewrite` 会重写报告正文并重新进行全局 QA。
- partial QA 只更新本轮返工维度的 QA 状态，未参与本轮返工的维度不会被误改。
- 因此本轮未通过维度只能是上一轮未通过维度的子集，避免漏检或目标漂移。

`QA_MAX_REVISION_ROUNDS` 控制自动返工上限。达到上限后，系统仍会进入 Report Finalizer，但最终报告会保留 QA 残留问题和质量摘要。

## 项目结构

```text
.
├── backend/
│   ├── alembic/                 # 数据库迁移
│   ├── app/
│   │   ├── agents/              # Planner 等轻量 Agent 封装
│   │   ├── api/                 # FastAPI 路由
│   │   ├── core/                # 配置、数据库、Celery、Redis runtime
│   │   ├── graph/               # 主 workflow
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic schema
│   │   ├── services/            # task、report、metrics、profile、matrix 等服务
│   │   └── tools/               # LLM、Milvus、Web context 工具
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── stores/
│   │   ├── types/
│   │   └── views/
│   └── package.json
├── tests/
└── README.md
```

## 数据库模型概览

| 表 | 说明 |
| --- | --- |
| `analysis_task` | 分析任务主表，保存用户输入、任务状态和最终 TaskPlan |
| `agent_node` | DAG 节点表，包含每个 Agent 的运行状态和动态维度 Agent 的当前 QA 状态 |
| `agent_run_log` | Agent 执行日志 |
| `source_document` | 采集到的网页资料 |
| `evidence_chunk` | 证据切块和向量 ID |
| `claim` | 结构化结论，包含 `dimension_key`、`dimension_label` 和 prompt spec |
| `claim_evidence` | Claim 与 evidence chunk 的关联 |
| `competitor_profile` | 动态竞品画像 |
| `comparison_matrix` | 动态对比矩阵 |
| `report` | 报告正文、HTML、JSON 结构和质量摘要 |
| `qa_result` | 每轮 QA 历史快照 |

最新迁移：

- `0004_agent_node_qa_state.py`：为 `agent_node` 增加维度 Agent 当前 QA 状态字段。

## API 概览

基础前缀：`/api/v1`

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/task-plans/parse` | 解析需求、自动发现竞品、自动补充维度 |
| `POST` | `/analysis-tasks` | 创建分析任务并入队 |
| `GET` | `/analysis-tasks` | 任务历史 |
| `GET` | `/analysis-tasks/{task_id}` | 任务详情 |
| `POST` | `/analysis-tasks/{task_id}/pause` | 暂停任务 |
| `POST` | `/analysis-tasks/{task_id}/resume` | 恢复任务 |
| `POST` | `/analysis-tasks/{task_id}/cancel` | 取消任务 |
| `POST` | `/analysis-tasks/{task_id}/retry` | 清理旧结果并重试 |
| `GET` | `/analysis-tasks/{task_id}/nodes` | DAG 节点和边，包含 QA 状态和返工高亮 |
| `GET` | `/analysis-tasks/{task_id}/logs` | Agent 日志 |
| `GET` | `/analysis-tasks/{task_id}/evidence` | 证据列表 |
| `GET` | `/analysis-tasks/{task_id}/claims` | Claim 列表 |
| `GET` | `/analysis-tasks/{task_id}/profiles` | 动态竞品画像 |
| `GET` | `/analysis-tasks/{task_id}/matrices` | 动态对比矩阵 |
| `GET` | `/analysis-tasks/{task_id}/metrics` | 运行指标 |
| `GET` | `/analysis-tasks/{task_id}/report` | 最新报告和关联数据 |
| `GET` | `/analysis-tasks/{task_id}/report/export?format=markdown` | 导出 Markdown |
| `GET` | `/analysis-tasks/{task_id}/report/export?format=pdf` | 导出 PDF |
| `GET` | `/analysis-tasks/{task_id}/qa` | 最新 QA 结果 |
| `GET` | `/analysis-tasks/{task_id}/qa/history` | QA 历史 |

## 环境变量

后端读取 `backend/.env`。

```env
APP_ENV=dev
APP_NAME=competitive-agent-system

DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/competitor_agent?charset=utf8mb4

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

FIRECRAWL_API_KEY=

MILVUS_URI=
MILVUS_TOKEN=
MILVUS_COLLECTION=evidence_chunks

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_THINKING_ENABLED=false
LLM_REASONING_EFFORT=high

EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

FIRECRAWL_SEARCH_RESULTS_PER_QUERY=3
FIRECRAWL_MAX_URLS_PER_COMPETITOR=20
COLLECTOR_MAX_WORKERS=4
EVIDENCE_EXTRACTOR_MAX_WORKERS=4
EVIDENCE_EMBEDDING_BATCH_SIZE=8

QA_MAX_REVISION_ROUNDS=1
REPORT_FINALIZER_MAX_REVISION_ROUNDS=2
QA_DIMENSION_PASS_THRESHOLD=0.70
QA_FINALIZER_PASS_THRESHOLD=0.75

RUN_TASKS_INLINE=false
FALLBACK_TO_LOCAL_THREAD_ON_CELERY_ERROR=true
FALLBACK_TO_LOCAL_THREAD_WHEN_WORKER_UNAVAILABLE=true
CELERY_WORKER_HEARTBEAT_TTL_SECONDS=45
CELERY_WORKER_HEARTBEAT_INTERVAL_SECONDS=10
CELERY_VISIBILITY_TIMEOUT_SECONDS=120
CELERY_QUEUED_RECOVERY_MAX_AGE_SECONDS=1800
```

## 本地启动

### 1. 后端依赖

```powershell
cd backend
conda activate competitor-agent
pip install -r requirements.txt
```

### 2. 数据库迁移

确保 MySQL 数据库已创建，并且 `backend/.env` 或 `backend/alembic.ini` 中的连接串正确。

```powershell
cd backend
D:\Anaconda\envs\competitor-agent\python.exe -m alembic upgrade head
```

查看当前迁移版本：

```powershell
D:\Anaconda\envs\competitor-agent\python.exe -m alembic current
```

迁移到最新版后，系统启动时会自动创建初始账号并把未归属的历史分析任务随机分配给这些账号：

- 管理员：`Admin` / `Admin`
- 测试用户：`User1` / `User1`、`User2` / `User2`、`User3` / `User3`

### 3. 启动 Redis

Redis 用于 Celery 队列、结果后端和 worker 心跳。请按本机环境启动 Redis，并确认 `CELERY_BROKER_URL` 可访问。

### 4. 启动后端 API

```powershell
cd backend
D:\Anaconda\envs\competitor-agent\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. 启动 Celery Worker

```powershell
cd backend
D:\Anaconda\envs\competitor-agent\python.exe -m celery -A app.worker worker --loglevel=info --pool=solo
```

开发时如果 Celery 不可用，系统可根据配置回退到本地线程执行任务。

### 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- OpenAPI：`http://127.0.0.1:8000/docs`

## 典型使用流程

1. 打开前端创建页。
2. 输入分析需求，例如：

   ```text
   请分析 Firecrawl 在 AI 数据采集领域的竞品情况，重点关注网页抓取能力、结构化抽取能力和开发者生态。
   ```

3. 点击解析需求。
4. 检查并编辑竞品、分析维度、输出语言和报告深度。
5. 点击开始分析。
6. 在任务详情页查看 DAG、日志、耗时、证据、Claim、QA 和报告。
7. 如 QA 不通过，系统会根据配置自动返工。
8. 报告完成后可导出 Markdown 或 PDF。

## 测试与验证

运行后端回归测试：

```powershell
D:\Anaconda\envs\competitor-agent\python.exe -m pytest tests/test_qa_revision_targets.py
```

编译检查：

```powershell
D:\Anaconda\envs\competitor-agent\python.exe -m py_compile backend/app/graph/workflow.py
```

前端构建：

```powershell
cd frontend
npm run build
```

当前已验证：

- QA 返工目标不会漏掉未通过维度。
- 第一轮全局 QA 后，所有未通过维度都会进入下一轮返工目标。
- partial QA 后，未通过维度集合只会从上一轮失败集合中收缩。
- `agent_node` 当前 QA 状态可作为返工调度的权威来源。
- 前端生产构建通过。构建时可能出现 Element Plus / Rolldown 的 pure annotation 和 chunk size 警告，不影响运行。

## 当前能力边界

- 系统依赖 Firecrawl、LLM API、Embedding API、Milvus、MySQL 和 Redis；外部服务不可用会影响完整流程。
- 自动竞品发现和自动维度推荐依赖 LLM 输出质量，前端保留人工确认入口。
- 资料采集质量取决于网页可访问性和 Firecrawl 返回内容。
- RAG 召回策略仍可继续优化，例如多 query 检索、来源权重、时间新鲜度和跨维度重排。
- QA 能发现常见证据缺失、维度遗漏、弱证据和写作结构问题，但仍建议对关键商业结论进行人工复核。
- PDF 导出依赖 `reportlab` 和字体环境，复杂宽表会按列分块以降低溢出风险。

## 开发约定

- 每个用户确认的分析维度对应一个动态维度 Agent。
- 动态维度 Agent 的真实执行失败会中断 workflow，避免生成空报告。
- `qa_result` 保存历史，`agent_node` 保存当前维度 QA 状态。
- 重试任务会清理旧报告、证据、Claim、QA 和 Agent QA 状态。
- 数据库结构变更必须新增 Alembic migration。
- 前端类型应与后端 Pydantic schema 保持同步。
