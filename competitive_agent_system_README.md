# AI 驱动的通用竞品分析 Agent 协作系统

> 本文档用于指导 Codex / Trae / Cursor 等 AI 编程助手进行项目开发。  
> 项目目标：构建一个通用竞品分析 Agent 协作系统，通过多 Agent DAG 流程自动完成公开资料采集、证据抽取、结构化分析、报告撰写、质检反馈和溯源展示。

---

## 1. 项目定位

本系统不是某个固定行业的竞品分析工具，而是一个 **通用竞品分析平台**。

MVP 阶段选择一个固定 Demo 场景用于验证系统能力：

```text
AI 编程助手 / AI IDE 竞品分析
竞品组合：Cursor、GitHub Copilot、Windsurf、Tabnine
```

MVP Demo 输入文本固定为：

```text
请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。
```

系统整体能力要设计成通用的，后续通过行业模板和 Schema 扩展到其他领域。

---

## 2. 最终确定技术栈

### 2.1 前端

```text
Vue 3
Vite
TypeScript
Element Plus
Vue Router
Pinia
VueFlow
ECharts
Axios
markdown-it
Prettier
ESLint
```

用途：

- Vue 3：前端主框架
- Vite：构建工具
- TypeScript：类型约束
- Element Plus：UI 组件库
- Vue Router：页面路由
- Pinia：全局状态管理
- VueFlow：DAG 节点可视化
- ECharts：统计图表
- Axios：请求后端 API
- markdown-it：渲染报告 Markdown

### 2.2 后端

```text
Python 3.11+
FastAPI
Pydantic
Pydantic Settings
SQLAlchemy
PyMySQL
Alembic
Uvicorn
```

用途：

- FastAPI：提供 REST API
- Pydantic：请求/响应/Agent State 数据建模
- SQLAlchemy：操作 MySQL
- Alembic：数据库迁移
- Uvicorn：运行 ASGI 服务

### 2.3 Agent 编排

```text
LangGraph
LangChain Core
```

分工：

```text
LangGraph：负责 Agent DAG、状态流转、分支、循环和 QA 反馈闭环
LangChain Core：负责模型调用、Prompt、结构化输出、Tool 抽象
```

### 2.4 数据库与检索

```text
MySQL 8：业务主库
Milvus：Evidence Chunk 向量检索
```

MySQL 存：

- 分析任务
- DAG 节点状态
- Agent 运行日志
- Source Document
- Evidence Chunk 元数据和正文
- Claim 分析结论
- Claim-Evidence 关联
- Report 报告
- QA 质检结果

Milvus 存：

- Evidence Chunk 的 embedding
- chunk_id
- task_id
- competitor_name
- source_type
- source_url 等检索过滤字段

### 2.5 异步任务

```text
Redis + Celery
```

MVP 阶段采用：

```text
一个用户分析任务 = 一个 Celery 后台任务
一个 Celery 任务内部 = 一次 LangGraph DAG 执行
每个 LangGraph 节点执行过程 = 写入 MySQL 日志
Redis = Celery Broker + 少量临时状态缓存
```

后续增强方案：

```text
多队列 + 多 Worker

crawl_queue       网页采集队列
embedding_queue   向量化队列
llm_queue         LLM 分析队列
report_queue      报告生成队列
```

### 2.6 采集层

MVP：

```text
Firecrawl Search + Firecrawl Scrape
```

增强：

```text
Tavily Search + Firecrawl Scrape + Playwright
```

展示亮点：

```text
支持 MCP 工具接入，未来可插拔 Playwright MCP / Firecrawl MCP
```

---

## 3. 总体架构

```text
Vue 前端
  |
  | REST API
  v
FastAPI 后端
  |
  | 创建任务 / 查询状态 / 查询报告 / 查询证据链
  v
MySQL 业务主库
  ^
  |
Celery Worker
  |
  | 执行 LangGraph DAG
  v
LangGraph Agent Workflow
  |
  | 调用
  v
Firecrawl / LLM / Milvus / MySQL
```

完整任务流：

```text
用户输入一句话
  ↓
Planner Agent 解析需求
  ↓
前端展示高级配置
  ↓
用户确认 / 修改配置
  ↓
FastAPI 创建任务
  ↓
Celery 后台执行 LangGraph
  ↓
Collector Agent 调用 Firecrawl Search/Scrape
  ↓
Evidence Extractor 抽取证据并切分 Chunk
  ↓
写入 MySQL + Milvus
  ↓
多个 Analyst Agent 生成结构化 Claim
  ↓
Writer Agent 生成 Markdown 报告
  ↓
QA Agent 质检
  ↓
通过：任务完成
  ↓
前端展示 DAG、证据链、报告、QA 结果
```

---

## 4. MVP 用户输入设计

MVP 阶段采用：

```text
一句话输入 + 高级配置确认/编辑
```

流程：

```text
1. 用户输入固定 Demo 文本
2. 点击“解析需求”
3. Planner Agent 解析为结构化 TaskPlan
4. 前端展示可编辑高级配置
5. 用户确认后点击“开始分析”
6. 后端创建 Celery 后台任务
7. 前端进入任务详情页查看进度
```

用户可编辑字段：

- 分析主题
- 行业领域
- 目标产品
- 竞品列表
- 分析维度
- 报告深度
- 输出语言
- 是否自动发现竞品
- 数据来源类型

---

## 5. 后端设计

### 5.1 后端目录结构

```text
backend/
├── app/
│   ├── main.py
│   ├── worker.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── celery_app.py
│   │   └── logging.py
│   ├── api/
│   │   ├── router.py
│   │   └── v1/
│   │       ├── task_plans.py
│   │       ├── analysis_tasks.py
│   │       ├── agent_nodes.py
│   │       ├── evidence.py
│   │       ├── reports.py
│   │       └── qa.py
│   ├── schemas/
│   │   ├── task_plan.py
│   │   ├── analysis_task.py
│   │   ├── agent_node.py
│   │   ├── evidence.py
│   │   ├── claim.py
│   │   ├── report.py
│   │   └── qa.py
│   ├── models/
│   │   ├── analysis_task.py
│   │   ├── agent_node.py
│   │   ├── agent_run_log.py
│   │   ├── source_document.py
│   │   ├── evidence_chunk.py
│   │   ├── claim.py
│   │   ├── claim_evidence.py
│   │   ├── report.py
│   │   └── qa_result.py
│   ├── repositories/
│   ├── services/
│   │   ├── task_service.py
│   │   ├── task_plan_service.py
│   │   ├── evidence_service.py
│   │   ├── claim_service.py
│   │   ├── report_service.py
│   │   ├── qa_service.py
│   │   └── log_service.py
│   ├── agents/
│   │   ├── planner_agent.py
│   │   ├── collector_agent.py
│   │   ├── evidence_extractor_agent.py
│   │   ├── feature_analyst_agent.py
│   │   ├── pricing_analyst_agent.py
│   │   ├── market_analyst_agent.py
│   │   ├── security_analyst_agent.py
│   │   ├── report_writer_agent.py
│   │   └── qa_agent.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── workflow.py
│   ├── tools/
│   │   ├── firecrawl_tool.py
│   │   ├── web_context_provider.py
│   │   ├── milvus_tool.py
│   │   └── llm_client.py
│   └── utils/
├── alembic/
├── requirements.txt
└── .env
```

---

## 6. LangGraph DAG 设计

### 6.1 MVP 节点

```text
PlannerNode
  ↓
CollectorNode
  ↓
EvidenceExtractorNode
  ↓
FeatureAnalysisNode
PricingAnalysisNode
MarketAnalysisNode
SecurityAnalysisNode
  ↓
ReportWriterNode
  ↓
QANode
  ↓
END
```

MVP 阶段可以先顺序执行分析节点，后续再做并行优化。

### 6.2 后续反馈闭环

后续增强：

```text
QANode 判断：
- 缺少证据 → 回到 CollectorNode
- 证据无法支撑结论 → 回到对应 AnalystNode
- 报告表达不清 → 回到 ReportWriterNode
- 通过 → END
```

### 6.3 Graph State

建议 Pydantic / TypedDict State：

```python
from typing import TypedDict, List, Optional, Dict, Any

class CompetitiveAnalysisState(TypedDict, total=False):
    task_id: int
    user_input: str
    task_plan: Dict[str, Any]

    competitors: List[str]
    analysis_dimensions: List[str]

    search_queries: List[str]
    source_document_ids: List[int]
    evidence_chunk_ids: List[int]
    claim_ids: List[int]

    report_id: Optional[int]
    qa_result_id: Optional[int]

    current_node: str
    next_action: str
    errors: List[str]
```

原则：

```text
State 中保存 ID 和少量摘要，不保存大段正文。
大段 Evidence、报告、日志都落 MySQL。
```

---

## 7. Agent 角色设计

### 7.1 Planner Agent

职责：

- 解析用户自然语言输入
- 生成结构化 TaskPlan
- 判断行业领域
- 提取竞品列表
- 提取分析维度
- 生成搜索方向

输出：

```json
{
  "topic": "AI 编程助手市场竞品分析",
  "industry": "AI 编程助手 / AI IDE",
  "target_product": null,
  "competitors": ["Cursor", "GitHub Copilot", "Windsurf", "Tabnine"],
  "analysis_dimensions": [
    "产品定位",
    "核心功能",
    "Agent 能力",
    "IDE 集成",
    "价格策略",
    "企业能力",
    "安全合规",
    "适用用户"
  ],
  "report_depth": "standard",
  "output_language": "zh-CN",
  "auto_discover_competitors": false,
  "data_sources": [
    "official_website",
    "pricing_page",
    "docs",
    "blog",
    "news",
    "reviews"
  ]
}
```

### 7.2 Collector Agent

职责：

- 根据 TaskPlan 生成搜索 query
- 调用 Firecrawl Search
- 调用 Firecrawl Scrape
- 保存 source_document

### 7.3 Evidence Extractor Agent

职责：

- 清洗网页正文
- 切分 chunk
- 提取关键 Evidence
- 写入 MySQL
- 调用 embedding
- 写入 Milvus

### 7.4 Analyst Agents

MVP 包含：

- FeatureAnalysisNode
- PricingAnalysisNode
- MarketAnalysisNode
- SecurityAnalysisNode

每个 Analyst 输出 Claim。

### 7.5 Report Writer Agent

职责：

- 基于 Claim 和 Evidence 生成 Markdown 报告
- 不允许编造没有 Evidence 支撑的核心结论
- 报告中的关键结论需要关联 evidence_chunk_id

### 7.6 QA Agent

职责：

- 检查核心 Claim 是否有 Evidence
- 检查价格信息是否有官方或可信来源
- 检查来源是否过旧
- 检查报告维度是否完整
- 输出 QAResult

---

## 8. 数据库设计

### 8.1 analysis_task

```sql
CREATE TABLE analysis_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_input TEXT NOT NULL,
  topic VARCHAR(255) NOT NULL,
  industry VARCHAR(255),
  target_product VARCHAR(255),
  status VARCHAR(50) NOT NULL,
  report_depth VARCHAR(50) DEFAULT 'standard',
  output_language VARCHAR(50) DEFAULT 'zh-CN',
  task_plan_json JSON,
  error_message TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

状态枚举建议：

```text
created
planned
queued
running
collecting
extracting
analyzing
writing
qa_checking
success
failed
cancelled
```

### 8.2 agent_node

```sql
CREATE TABLE agent_node (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  node_key VARCHAR(100) NOT NULL,
  node_name VARCHAR(255) NOT NULL,
  node_type VARCHAR(100) NOT NULL,
  status VARCHAR(50) NOT NULL,
  input_summary TEXT,
  output_summary TEXT,
  started_at DATETIME NULL,
  ended_at DATETIME NULL,
  duration_ms INT NULL,
  retry_count INT DEFAULT 0,
  error_message TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 8.3 agent_run_log

```sql
CREATE TABLE agent_run_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  node_id BIGINT,
  log_type VARCHAR(50) NOT NULL,
  message TEXT NOT NULL,
  payload_json JSON,
  created_at DATETIME NOT NULL
);
```

### 8.4 source_document

```sql
CREATE TABLE source_document (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  competitor_name VARCHAR(255),
  source_url TEXT NOT NULL,
  source_title VARCHAR(500),
  source_type VARCHAR(100),
  content_markdown MEDIUMTEXT,
  content_text MEDIUMTEXT,
  metadata_json JSON,
  fetched_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL
);
```

### 8.5 evidence_chunk

```sql
CREATE TABLE evidence_chunk (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  source_document_id BIGINT NOT NULL,
  competitor_name VARCHAR(255),
  source_url TEXT NOT NULL,
  source_title VARCHAR(500),
  source_type VARCHAR(100),
  chunk_index INT NOT NULL,
  chunk_text TEXT NOT NULL,
  reliability_score DECIMAL(4,2),
  milvus_vector_id VARCHAR(128),
  created_at DATETIME NOT NULL
);
```

### 8.6 claim

```sql
CREATE TABLE claim (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  agent_node_id BIGINT,
  competitor_name VARCHAR(255),
  claim_type VARCHAR(100),
  claim_text TEXT NOT NULL,
  confidence DECIMAL(4,2),
  risk_level VARCHAR(50),
  created_at DATETIME NOT NULL
);
```

### 8.7 claim_evidence

```sql
CREATE TABLE claim_evidence (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  claim_id BIGINT NOT NULL,
  evidence_chunk_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL
);
```

### 8.8 report

```sql
CREATE TABLE report (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  title VARCHAR(255) NOT NULL,
  content_markdown MEDIUMTEXT NOT NULL,
  content_html MEDIUMTEXT,
  report_json JSON,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 8.9 qa_result

```sql
CREATE TABLE qa_result (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  report_id BIGINT,
  passed BOOLEAN NOT NULL,
  score DECIMAL(4,2),
  issues_json JSON,
  created_at DATETIME NOT NULL
);
```

---

## 9. Milvus Collection 设计

Collection 名称：

```text
evidence_chunks
```

字段建议：

```text
id: int64, primary key
task_id: int64
chunk_id: int64
competitor_name: varchar
source_type: varchar
source_url: varchar
embedding: float_vector
```

向量维度取决于 embedding 模型，例如：

```text
text-embedding-3-small: 1536
```

注意：

```text
Milvus 只负责语义召回。
Evidence 原文、URL、标题、来源、Claim 关联关系必须以 MySQL 为准。
```

---

## 10. 后端 API 设计

前端和后端必须通过明确的 API Contract 对齐。  
MVP 统一使用 `snake_case` JSON 字段，和 FastAPI / Pydantic 保持一致。Vue TypeScript 中也直接使用 snake_case，避免字段转换错误。

所有 API 统一前缀：

```text
/api/v1
```

---

### 10.1 解析用户输入

```http
POST /api/v1/task-plans/parse
```

请求：

```json
{
  "user_input": "请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。"
}
```

响应：

```json
{
  "task_plan": {
    "topic": "AI 编程助手市场竞品分析",
    "industry": "AI 编程助手 / AI IDE",
    "target_product": null,
    "competitors": ["Cursor", "GitHub Copilot", "Windsurf", "Tabnine"],
    "analysis_dimensions": [
      "产品定位",
      "核心功能",
      "Agent 能力",
      "IDE 集成",
      "价格策略",
      "企业能力",
      "安全合规",
      "适用用户"
    ],
    "report_depth": "standard",
    "output_language": "zh-CN",
    "auto_discover_competitors": false,
    "data_sources": [
      "official_website",
      "pricing_page",
      "docs",
      "blog",
      "news",
      "reviews"
    ]
  }
}
```

---

### 10.2 创建分析任务

```http
POST /api/v1/analysis-tasks
```

请求：

```json
{
  "user_input": "请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况...",
  "task_plan": {
    "topic": "AI 编程助手市场竞品分析",
    "industry": "AI 编程助手 / AI IDE",
    "target_product": null,
    "competitors": ["Cursor", "GitHub Copilot", "Windsurf", "Tabnine"],
    "analysis_dimensions": ["产品定位", "核心功能", "Agent 能力", "IDE 集成", "价格策略"],
    "report_depth": "standard",
    "output_language": "zh-CN",
    "auto_discover_competitors": false,
    "data_sources": ["official_website", "pricing_page", "docs", "blog"]
  }
}
```

响应：

```json
{
  "task_id": 1001,
  "status": "queued"
}
```

后端行为：

```text
1. 写入 analysis_task
2. 初始化 agent_node
3. 通过 Celery 投递 run_analysis_task(task_id)
4. 返回 task_id
```

---

### 10.3 查询任务详情

```http
GET /api/v1/analysis-tasks/{task_id}
```

响应：

```json
{
  "id": 1001,
  "user_input": "...",
  "topic": "AI 编程助手市场竞品分析",
  "industry": "AI 编程助手 / AI IDE",
  "status": "running",
  "report_depth": "standard",
  "output_language": "zh-CN",
  "task_plan": {},
  "created_at": "2026-05-24T10:00:00",
  "updated_at": "2026-05-24T10:02:00"
}
```

---

### 10.4 查询 DAG 节点

```http
GET /api/v1/analysis-tasks/{task_id}/nodes
```

响应：

```json
{
  "nodes": [
    {
      "id": 1,
      "task_id": 1001,
      "node_key": "planner",
      "node_name": "任务规划 Agent",
      "node_type": "planner",
      "status": "success",
      "input_summary": "...",
      "output_summary": "...",
      "started_at": "2026-05-24T10:00:01",
      "ended_at": "2026-05-24T10:00:05",
      "duration_ms": 4000,
      "retry_count": 0,
      "error_message": null
    }
  ],
  "edges": [
    { "source": "planner", "target": "collector" },
    { "source": "collector", "target": "evidence_extractor" },
    { "source": "evidence_extractor", "target": "feature_analysis" },
    { "source": "feature_analysis", "target": "report_writer" },
    { "source": "report_writer", "target": "qa" }
  ]
}
```

前端 VueFlow 使用这个接口渲染 DAG。

---

### 10.5 查询 Agent 日志

```http
GET /api/v1/analysis-tasks/{task_id}/logs
```

可选 query：

```text
?node_key=collector
```

响应：

```json
{
  "logs": [
    {
      "id": 1,
      "task_id": 1001,
      "node_id": 2,
      "log_type": "info",
      "message": "Firecrawl search completed",
      "payload": {
        "query": "Cursor AI pricing official",
        "result_count": 5
      },
      "created_at": "2026-05-24T10:01:00"
    }
  ]
}
```

---

### 10.6 查询 Evidence

```http
GET /api/v1/analysis-tasks/{task_id}/evidence
```

可选 query：

```text
?competitor_name=Cursor
?source_type=pricing_page
```

响应：

```json
{
  "items": [
    {
      "id": 11,
      "task_id": 1001,
      "competitor_name": "Cursor",
      "source_url": "https://cursor.com/pricing",
      "source_title": "Cursor Pricing",
      "source_type": "pricing_page",
      "chunk_index": 0,
      "chunk_text": "...",
      "reliability_score": 0.95,
      "created_at": "2026-05-24T10:01:30"
    }
  ]
}
```

---

### 10.7 查询 Claim

```http
GET /api/v1/analysis-tasks/{task_id}/claims
```

响应：

```json
{
  "items": [
    {
      "id": 201,
      "task_id": 1001,
      "competitor_name": "Cursor",
      "claim_type": "pricing",
      "claim_text": "Cursor 采用面向个人和团队的订阅式定价策略。",
      "confidence": 0.86,
      "risk_level": "low",
      "evidence_ids": [11, 12]
    }
  ]
}
```

---

### 10.8 查询报告

```http
GET /api/v1/analysis-tasks/{task_id}/report
```

响应：

```json
{
  "report": {
    "id": 301,
    "task_id": 1001,
    "title": "AI 编程助手市场竞品分析报告",
    "content_markdown": "# AI 编程助手市场竞品分析报告\n\n...",
    "content_html": "<h1>AI 编程助手市场竞品分析报告</h1>",
    "created_at": "2026-05-24T10:05:00",
    "updated_at": "2026-05-24T10:05:00"
  }
}
```

---

### 10.9 查询 QA 结果

```http
GET /api/v1/analysis-tasks/{task_id}/qa
```

响应：

```json
{
  "qa_result": {
    "id": 401,
    "task_id": 1001,
    "report_id": 301,
    "passed": true,
    "score": 0.88,
    "issues": [
      {
        "type": "weak_evidence",
        "severity": "medium",
        "message": "Tabnine 的部分企业安全结论只有官网来源，缺少第三方佐证。",
        "related_claim_id": 208,
        "suggested_action": "reanalyze"
      }
    ],
    "created_at": "2026-05-24T10:06:00"
  }
}
```

---

## 11. 前端设计

### 11.1 前端目录结构

```text
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   │   └── index.ts
│   ├── api/
│   │   ├── http.ts
│   │   ├── taskPlanApi.ts
│   │   ├── analysisTaskApi.ts
│   │   ├── evidenceApi.ts
│   │   └── reportApi.ts
│   ├── types/
│   │   ├── taskPlan.ts
│   │   ├── analysisTask.ts
│   │   ├── agentNode.ts
│   │   ├── evidence.ts
│   │   ├── claim.ts
│   │   ├── report.ts
│   │   └── qa.ts
│   ├── stores/
│   │   └── analysisTaskStore.ts
│   ├── views/
│   │   ├── TaskCreateView.vue
│   │   ├── TaskDetailView.vue
│   │   ├── ReportView.vue
│   │   └── EvidenceView.vue
│   └── components/
│       ├── TaskPlanForm.vue
│       ├── DagFlow.vue
│       ├── AgentNodeDrawer.vue
│       ├── EvidenceList.vue
│       ├── ClaimList.vue
│       ├── ReportMarkdown.vue
│       └── QaResultPanel.vue
├── package.json
└── vite.config.ts
```

---

### 11.2 页面设计

#### TaskCreateView

功能：

- 展示 Demo 固定输入文本
- 点击“解析需求”
- 调用 `/api/v1/task-plans/parse`
- 展示 TaskPlanForm
- 用户编辑高级配置
- 点击“开始分析”
- 调用 `/api/v1/analysis-tasks`
- 跳转任务详情页

#### TaskDetailView

功能：

- 展示任务状态
- 展示 DAG 流程图
- 轮询任务详情和节点状态
- 展示 Agent 日志
- 提供进入报告页和证据页按钮

#### ReportView

功能：

- 调用 `/api/v1/analysis-tasks/{task_id}/report`
- 使用 markdown-it 渲染报告
- 展示 QA 结果
- 展示报告相关 Claim 和 Evidence

#### EvidenceView

功能：

- 调用 `/api/v1/analysis-tasks/{task_id}/evidence`
- 按竞品、来源类型筛选
- 点击 Evidence 查看原文片段和来源 URL
- 展示该 Evidence 支撑了哪些 Claim

---

## 12. 前后端接口对齐规则

必须将前端和后端设计分开写，同时用 API Contract 对齐。推荐文档结构：

```text
1. 总体架构
2. 后端设计
3. 前端设计
4. API Contract
5. 数据库设计
6. 开发顺序
```

对齐规则：

```text
1. 后端 Pydantic Schema 是接口源头
2. 前端 TypeScript interface 必须和 API 响应一致
3. MVP 统一使用 snake_case 字段
4. 不允许前端直接访问 MySQL、Milvus、Redis
5. 所有数据都通过 FastAPI 获取
6. 后端所有接口统一 /api/v1 前缀
7. 前端 axios baseURL 指向 VITE_API_BASE_URL
8. 后续可用 OpenAPI 生成 TypeScript 类型，但 MVP 可以手写
```

### 12.1 前端环境变量

`frontend/.env.development`

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

### 12.2 Axios 封装

```ts
import axios from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
})
```

### 12.3 TypeScript 类型示例

```ts
export interface TaskPlan {
  topic: string
  industry?: string | null
  target_product?: string | null
  competitors: string[]
  analysis_dimensions: string[]
  report_depth: 'simple' | 'standard' | 'deep'
  output_language: string
  auto_discover_competitors: boolean
  data_sources: string[]
}

export interface AnalysisTask {
  id: number
  user_input: string
  topic: string
  industry?: string | null
  status: string
  report_depth: string
  output_language: string
  task_plan: TaskPlan
  created_at: string
  updated_at: string
}

export interface AgentNode {
  id: number
  task_id: number
  node_key: string
  node_name: string
  node_type: string
  status: string
  input_summary?: string | null
  output_summary?: string | null
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  retry_count: number
  error_message?: string | null
}
```

---

## 13. Celery 任务设计

### 13.1 Celery App

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "competitive_agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
)
```

### 13.2 后台任务

```python
@celery_app.task(bind=True, max_retries=3)
def run_analysis_task(self, task_id: int):
    try:
        task_service.update_status(task_id, "running")

        graph = build_competitive_analysis_graph()
        graph.invoke({"task_id": task_id})

        task_service.update_status(task_id, "success")

    except Exception as exc:
        task_service.update_status(task_id, "failed", error_message=str(exc))
        raise self.retry(exc=exc, countdown=30)
```

---

## 14. 采集层设计

### 14.1 WebContextProvider

Agent 不直接调用 Firecrawl，而是调用统一工具层：

```python
class WebContextProvider:
    def search(self, query: str, max_results: int = 5):
        ...

    def scrape(self, url: str):
        ...
```

MVP 底层实现：

```text
search → Firecrawl Search
scrape → Firecrawl Scrape
```

增强：

```text
search → Tavily Search
scrape → Firecrawl Scrape
dynamic_page → Playwright
mcp → Playwright MCP / Firecrawl MCP
```

### 14.2 Evidence 处理流程

```text
Firecrawl Search
  ↓
得到候选 URL
  ↓
Firecrawl Scrape
  ↓
得到 markdown / text
  ↓
SourceDocument 写 MySQL
  ↓
文本清洗与 chunk 切分
  ↓
EvidenceChunk 写 MySQL
  ↓
生成 embedding
  ↓
写入 Milvus
```

---

## 15. QA 规则

MVP QA Agent 至少检查：

```text
1. 每个核心 Claim 是否绑定 Evidence
2. 价格类 Claim 是否有 pricing_page 或 official_website 来源
3. 安全合规类 Claim 是否有官方安全/企业页面来源
4. 报告是否覆盖用户选择的分析维度
5. Evidence 来源是否为空
6. Claim 置信度过低时是否标记 risk_level
```

QAIssue 类型：

```text
missing_evidence
weak_evidence
unsupported_claim
contradiction
outdated_source
schema_incomplete
logic_gap
```

---

## 16. 后端环境变量

`backend/.env`

```env
APP_ENV=dev
APP_NAME=competitive-agent-system

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=competitor_agent
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=competitor_agent
DATABASE_URL=mysql+pymysql://competitor_agent:your_password@127.0.0.1:3306/competitor_agent?charset=utf8mb4

# Redis / Celery
REDIS_HOST=your_server_ip
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0
CELERY_BROKER_URL=redis://:your_redis_password@your_server_ip:6379/0
CELERY_RESULT_BACKEND=redis://:your_redis_password@your_server_ip:6379/1

# Milvus
MILVUS_URI=http://your_server_ip:19530
MILVUS_TOKEN=competitor_agent:your_password
MILVUS_COLLECTION=evidence_chunks

# Firecrawl
FIRECRAWL_API_KEY=fc-your-api-key

# LLM
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

不要把 `.env` 提交到 Git。

---

## 17. 推荐开发顺序

### Phase 1：项目骨架

```text
1. 创建 backend FastAPI 项目结构
2. 创建 frontend Vue 项目结构
3. 配置 .env
4. 配置 MySQL 连接
5. 配置 Redis + Celery
6. 配置基本 API 路由
```

### Phase 2：任务创建闭环

```text
1. 实现 /task-plans/parse
2. 实现 TaskCreateView
3. 实现高级配置表单
4. 实现 /analysis-tasks
5. 创建任务后投递 Celery
6. 前端跳转 TaskDetailView
```

### Phase 3：DAG 与日志

```text
1. 实现 LangGraph 基础 workflow
2. 实现 PlannerNode / CollectorNode / WriterNode / QANode 的 mock 版本
3. 每个节点写 agent_node 和 agent_run_log
4. 实现 /nodes /logs 接口
5. 前端 VueFlow 展示 DAG
```

### Phase 4：真实采集

```text
1. 接入 Firecrawl Search
2. 接入 Firecrawl Scrape
3. 保存 source_document
4. 保存 evidence_chunk
5. 前端展示 Evidence
```

### Phase 5：Milvus 与分析

```text
1. 接入 embedding
2. 写入 Milvus
3. 实现 Analyst Agent
4. 保存 Claim
5. Claim 绑定 Evidence
```

### Phase 6：报告与 QA

```text
1. ReportWriter 生成 Markdown
2. QAAgent 检查报告
3. 保存 report 和 qa_result
4. 前端展示报告、QA、证据链
```

### Phase 7：演示打磨

```text
1. 固定 Demo 输入
2. 优化任务进度展示
3. 优化报告页面
4. 优化证据链页面
5. 添加统计图表
6. 准备答辩说明
```

---

## 18. AI 编程助手开发要求

给 Codex / Trae / Cursor 的开发要求：

```text
1. 优先实现可跑通的 MVP，不要过早做复杂抽象。
2. 前后端必须按本文档 API Contract 对齐。
3. 后端接口字段统一 snake_case。
4. 前端 TypeScript interface 必须和接口响应一致。
5. 所有核心业务数据写 MySQL，不允许只存在 Redis。
6. Milvus 只用于 Evidence Chunk 向量召回。
7. Celery 只负责后台执行，不负责业务状态最终存储。
8. LangGraph 节点必须在执行前后写入 agent_node / agent_run_log。
9. 报告中的核心结论必须能追溯到 Claim 和 Evidence。
10. 不要把 API Key、数据库密码写入代码。
11. MVP 先用 Firecrawl Search + Firecrawl Scrape，不要先接 Playwright / MCP。
12. 先 mock LLM 输出跑通链路，再逐步替换成真实 LLM。
```

---

## 19. MVP 验收标准

MVP 完成时需要达到：

```text
1. 前端可以输入 Demo 文本
2. Planner 可以解析出 TaskPlan
3. 前端可以编辑高级配置
4. 用户可以创建分析任务
5. Celery 可以后台执行任务
6. LangGraph 可以执行一条完整 DAG
7. 每个节点状态可以写入 MySQL
8. 前端可以用 VueFlow 展示 DAG
9. Collector 可以调用 Firecrawl 获取资料
10. Evidence 可以写入 MySQL
11. Evidence embedding 可以写入 Milvus
12. Analyst 可以生成 Claim
13. Claim 可以绑定 Evidence
14. Writer 可以生成 Markdown 报告
15. QA 可以生成质检结果
16. 前端可以展示报告、证据链和 QA 结果
```

---

## 20. 最终说明

该项目的核心展示点不是“一个大模型生成报告”，而是：

```text
多 Agent 协作
LangGraph DAG 流转
公开资料采集
Evidence / Claim 结构化
MySQL + Milvus 证据存储与检索
QA 质检反馈
全过程可观测
报告结论可溯源
```

MVP Demo 使用 AI 编程助手赛道，但系统设计必须保持通用性，后续通过行业模板和 Schema 扩展支持更多领域。
