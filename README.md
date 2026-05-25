# Competitive Agent

AI 驱动的通用竞品分析 Agent 协作系统。项目把“一句话竞品分析需求”解析成结构化任务计划，再通过多个 Agent 按 DAG 流程完成资料采集、证据抽取、结构化分析、报告生成和质量检查。任务状态、节点进度、Agent 日志、网页来源、证据、结论、报告和 QA 结果都会落到 MySQL，证据向量会写入 Milvus，前端通过 Vue 实时展示完整执行过程。

当前版本已经接入真实外部服务：

- Firecrawl：搜索和抓取公开网页。
- LLM：解析需求、生成 Claim、撰写报告、执行 QA 复核。
- Embedding：把网页证据切片转成向量。
- Milvus：保存 Evidence Chunk 向量。
- Redis + Celery：异步执行长任务。

## 整体架构

```text
用户浏览器
   |
   | Vue 3 / Axios
   v
FastAPI API
   |
   | 1. 解析需求 / 创建任务
   | 2. 查询任务、DAG、日志、证据、报告
   v
MySQL <---------------------------+
   |                              |
   | 保存任务、节点、日志、证据、结论 |
   |                              |
Redis Queue                       |
   |                              |
   v                              |
Celery Worker                     |
   |                              |
   | 执行多 Agent DAG              |
   v                              |
Firecrawl / LLM / Embedding / Milvus
```

核心思想是把长时间运行的分析流程从 HTTP 请求中拆出去。前端创建任务后立即拿到 `task_id`，随后轮询后端接口展示 DAG 节点状态和 Agent 日志；Celery Worker 在后台执行真实采集、分析和写库。

## 技术框架

### 前端

- Vue 3 + TypeScript：页面和状态组织。
- Vite：开发服务器和构建工具。
- Element Plus：表单、按钮、折叠面板、时间线、标签等 UI 组件。
- VueFlow：展示 Agent DAG。
- Axios：调用后端 API。
- markdown-it：渲染 Markdown 报告。

### 后端

- FastAPI：REST API 服务。
- Pydantic / pydantic-settings：请求响应 Schema 和环境变量配置。
- SQLAlchemy：ORM 模型和数据库访问。
- PyMySQL：连接 MySQL。
- Alembic：数据库迁移。
- Celery：后台异步任务执行。
- Redis：Celery Broker、Worker 心跳。
- pymilvus：写入和查询 Milvus 向量库。
- langchain-openai / openai：调用 OpenAI 兼容 LLM 和 Embedding API。

### 数据存储

- MySQL：系统主数据库，保存可审计业务数据。
- Milvus：向量数据库，保存 Evidence Chunk 的 embedding。
- Redis：消息队列和 Worker 在线心跳，不保存业务最终结果。

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── agents/       # Planner Agent 等 Agent 入口
│   │   ├── core/         # 配置、数据库、Celery、日志、Redis 运行态
│   │   ├── graph/        # 多 Agent DAG 工作流
│   │   ├── models/       # SQLAlchemy 数据模型
│   │   ├── schemas/      # Pydantic API Schema
│   │   ├── services/     # 任务、日志、证据、报告等业务服务
│   │   └── tools/        # Firecrawl / Milvus / LLM 工具层
│   ├── alembic/          # Alembic 迁移
│   ├── requirements.txt
│   └── .env              # 本地后端配置，不提交
├── frontend/
│   ├── src/
│   │   ├── api/          # Axios API 封装
│   │   ├── components/   # DAG、证据、报告、QA 等组件
│   │   ├── router/
│   │   ├── stores/
│   │   ├── types/
│   │   └── views/
│   └── package.json
└── competitive_agent_system_README.md
```

## Agent 设计

系统当前固定创建 9 个 DAG 节点。节点定义在 `backend/app/services/task_service.py`，执行逻辑在 `backend/app/graph/workflow.py`。

| node_key | Agent | 作用 | 主要输入 | 主要输出 |
| --- | --- | --- | --- | --- |
| `planner` | 任务规划 Agent | 把用户输入解析为结构化 TaskPlan | `user_input` | 竞品列表、行业、分析维度、报告深度 |
| `collector` | 资料采集 Agent | 按竞品生成搜索 query，调用 Firecrawl Search / Scrape | TaskPlan | `source_document` |
| `evidence_extractor` | 证据抽取 Agent | 清洗网页文本、切片、生成 embedding、写入 MySQL 和 Milvus | `source_document` | `evidence_chunk`、Milvus 向量 |
| `feature_analysis` | 功能分析 Agent | 基于证据分析产品定位、功能、IDE/Agent 能力 | `evidence_chunk` | feature 类型 `claim` |
| `pricing_analysis` | 价格分析 Agent | 分析套餐、价格策略、个人和团队商业化 | `evidence_chunk` | pricing 类型 `claim` |
| `market_analysis` | 市场分析 Agent | 分析用户群体、市场定位、企业能力 | `evidence_chunk` | market 类型 `claim` |
| `security_analysis` | 安全合规分析 Agent | 分析隐私、安全、合规、企业治理 | `evidence_chunk` | security 类型 `claim` |
| `report_writer` | 报告撰写 Agent | 基于 Claim 写 Markdown 竞品分析报告 | `claim`、`claim_evidence` | `report` |
| `qa` | 质量检查 Agent | 规则检查 + LLM 复核报告质量和证据支撑 | `report`、`claim` | `qa_result` |

### DAG 顺序

```text
planner
  -> collector
  -> evidence_extractor
  -> feature_analysis
  -> pricing_analysis
  -> market_analysis
  -> security_analysis
  -> report_writer
  -> qa
```

每个节点执行时都会更新 `agent_node.status`，并写入 `agent_run_log`。前端任务详情页通过轮询 `/analysis-tasks/{task_id}`、`/nodes`、`/logs` 实时展示流程。

## 数据流转

### 1. 解析需求

前端调用：

```text
POST /api/v1/task-plans/parse
```

后端使用 Planner Agent 调用 LLM，把自然语言解析成 TaskPlan。TaskPlan 包含：

- `topic`
- `industry`
- `target_product`
- `competitors`
- `analysis_dimensions`
- `report_depth`
- `output_language`
- `auto_discover_competitors`

### 2. 创建分析任务

前端调用：

```text
POST /api/v1/analysis-tasks
```

后端创建：

- 1 条 `analysis_task`
- 9 条 `agent_node`

如果 Worker 心跳存在，任务会进入 Redis 队列 `competitor_agent_analysis`；如果开发环境没有 Worker 或 Redis 暂时不可用，会按配置降级到本地后台线程执行。

### 3. Worker 执行 DAG

Celery Worker 收到任务后调用：

```text
run_competitive_analysis(db, task_id)
```

执行过程：

1. `planner` 重新生成或校准 TaskPlan。
2. `collector` 对每个竞品生成搜索 query，Firecrawl 搜索并抓取网页。
3. 抓取结果写入 `source_document`。
4. `evidence_extractor` 清洗网页正文，按约 1400 字符切片。
5. 每个切片调用 embedding。
6. 每个切片写入 `evidence_chunk`，向量写入 Milvus collection `evidence_chunks`。
7. 各分析 Agent 用 evidence context 调 LLM，生成结构化 Claim。
8. Claim 与 Evidence 通过 `claim_evidence` 建立引用关系。
9. `report_writer` 基于 Claim 生成 Markdown 报告。
10. `qa` 做证据完整性、置信度、维度覆盖检查，并调用 LLM 复核。

### 4. 前端展示

前端主要页面：

- 创建页：输入需求、解析 TaskPlan、创建任务。
- 任务详情页：展示任务状态、DAG、节点卡片、按 Agent 折叠的日志。
- 证据链页：查看 `evidence_chunk` 和来源 URL。
- 报告页：查看 Markdown 报告、QA 结果、Claim。

## 数据库设计

### `analysis_task`

任务主表。

| 字段 | 含义 |
| --- | --- |
| `id` | 任务 ID |
| `user_input` | 用户原始需求 |
| `topic` | 分析主题 |
| `industry` | 行业 |
| `target_product` | 目标产品 |
| `status` | 任务状态，如 `queued`、`collecting`、`extracting`、`analyzing`、`success`、`failed` |
| `report_depth` | 报告深度 |
| `output_language` | 输出语言 |
| `task_plan_json` | 结构化 TaskPlan |
| `error_message` | 失败原因 |

### `agent_node`

每个任务的 Agent DAG 节点。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `node_key` | 节点标识 |
| `node_name` | 展示名称 |
| `node_type` | 节点类型 |
| `status` | `pending`、`running`、`success`、`failed` |
| `input_summary` | 输入摘要 |
| `output_summary` | 输出摘要 |
| `started_at` / `ended_at` | 开始和结束时间 |
| `duration_ms` | 执行耗时 |
| `error_message` | 节点错误 |

### `agent_run_log`

Agent 运行日志。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `node_id` | 所属节点，可为空 |
| `log_type` | `info`、`warning`、`error` |
| `message` | 日志消息 |
| `payload_json` | 结构化上下文 |
| `created_at` | 记录时间 |

### `source_document`

Firecrawl 抓取到的网页文档。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `competitor_name` | 竞品名 |
| `source_url` | 来源 URL |
| `source_title` | 网页标题 |
| `source_type` | 来源类型，如 `official_website`、`pricing_page`、`docs` |
| `content_markdown` | 原始 Markdown |
| `content_text` | 清洗后的文本 |
| `metadata_json` | 搜索 query、搜索结果、抓取元数据 |

### `evidence_chunk`

网页文档切片后的证据块。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `source_document_id` | 来源文档 |
| `competitor_name` | 竞品名 |
| `source_url` / `source_title` | 来源信息 |
| `source_type` | 来源类型 |
| `chunk_index` | 文档内切片序号 |
| `chunk_text` | 证据文本 |
| `reliability_score` | 证据可信度评分 |
| `milvus_vector_id` | Milvus 向量 ID，正常为 `task_id-chunk_id` |

Milvus collection `evidence_chunks` 字段包括：

- `id`
- `task_id`
- `chunk_id`
- `competitor_name`
- `source_type`
- `source_url`
- `embedding`

### `claim`

分析 Agent 生成的结构化结论。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `agent_node_id` | 生成该 Claim 的 Agent 节点 |
| `competitor_name` | 竞品名 |
| `claim_type` | `feature`、`pricing`、`market`、`security` |
| `claim_text` | 结论文本 |
| `confidence` | 置信度 |
| `risk_level` | 风险等级 |

### `claim_evidence`

Claim 与 Evidence 的多对多关联表。

| 字段 | 含义 |
| --- | --- |
| `claim_id` | Claim ID |
| `evidence_chunk_id` | Evidence Chunk ID |

### `report`

最终报告。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `title` | 报告标题 |
| `content_markdown` | Markdown 内容 |
| `content_html` | HTML 内容 |
| `report_json` | 报告元数据，如 Claim ID 列表 |

### `qa_result`

报告质量检查结果。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 所属任务 |
| `report_id` | 报告 ID |
| `passed` | 是否通过 |
| `score` | QA 得分 |
| `issues_json` | 问题列表 |

## API 概览

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/task-plans/parse` | 解析自然语言需求为 TaskPlan |
| `POST` | `/api/v1/analysis-tasks` | 创建分析任务 |
| `GET` | `/api/v1/analysis-tasks/{task_id}` | 查询任务详情 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/nodes` | 查询 DAG 节点和边 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/logs` | 查询 Agent 日志 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/evidence` | 查询证据链 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/claims` | 查询结构化 Claim |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report` | 查询报告 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/qa` | 查询 QA 结果 |

## 配置流程

### 1. 创建 Conda 环境

```powershell
conda create -n competitor-agent python=3.11
conda activate competitor-agent
```

### 2. 安装后端依赖

```powershell
cd backend
pip install -r requirements.txt
```

### 3. 安装前端依赖

```powershell
cd frontend
npm install
```

### 4. 创建 MySQL 数据库

```sql
CREATE DATABASE competitor_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 配置后端 `.env`

在 `backend/.env` 中配置：

```env
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/competitor_agent?charset=utf8mb4

CELERY_BROKER_URL=redis://:password@43.143.122.92:6379/0
CELERY_RESULT_BACKEND=redis://:password@43.143.122.92:6379/1

FIRECRAWL_API_KEY=你的 Firecrawl Key

LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=你的 LLM Key
LLM_MODEL=deepseek-v4-flash
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1536

MILVUS_URI=http://43.143.122.92:19530
MILVUS_TOKEN=你的 Milvus Token
MILVUS_COLLECTION=evidence_chunks

RUN_TASKS_INLINE=false
FALLBACK_TO_LOCAL_THREAD_ON_CELERY_ERROR=true
FALLBACK_TO_LOCAL_THREAD_WHEN_WORKER_UNAVAILABLE=true
```

### 6. 配置前端 `.env.development`

在 `frontend/.env.development` 中配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

### 7. 初始化数据库

```powershell
cd backend
conda activate competitor-agent
python -m app.db_init
```

也可以使用 Alembic：

```powershell
alembic upgrade head
```

## 启动项目

### 启动后端 API

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 启动 Celery Worker

另开终端：

```powershell
cd D:\Code\Python\Competitor-Agent\backend
conda activate competitor-agent
python -m celery -A app.worker:celery_app worker --loglevel=info --pool=solo -Q competitor_agent_analysis --without-gossip --without-mingle --without-heartbeat
```

Windows 本地建议使用 `python -m celery` 和 `--pool=solo`。不要用 `conda run celery ...` 包装长进程，否则日志和进程行为不够直观。

### 启动前端

另开终端：

```powershell
cd D:\Code\Python\Competitor-Agent\frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173/
```

## 使用流程

1. 打开前端首页。
2. 输入竞品分析需求。
3. 点击“解析需求”，由 Planner Agent 生成 TaskPlan。
4. 检查竞品、行业、分析维度、输出语言等配置。
5. 点击“开始分析”。
6. 进入任务详情页，查看 DAG 节点、进度、Agent 动态日志。
7. 进入证据链页，查看 Evidence Chunk 和来源 URL。
8. 进入报告页，查看 Markdown 报告、Claim 和 QA 结果。

## Redis 与 Celery 运行说明

当前项目使用专用队列：

```text
competitor_agent_analysis
```

Worker 心跳 key：

```text
competitor_agent:worker:heartbeat
```

Celery 还会创建 Kombu 内部绑定 key：

```text
_kombu.binding.competitor_agent_analysis
```

当前代码关闭了 Kombu Redis `ack_emulation`，用于规避远程 Redis 长时间空闲后断开连接导致消息卡在 `unacked` 的问题。远程 Redis 服务端建议设置：

```bash
redis-cli -h 43.143.122.92 -p 6379 -a '你的 Redis 密码' CONFIG SET timeout 0
redis-cli -h 43.143.122.92 -p 6379 -a '你的 Redis 密码' CONFIG SET tcp-keepalive 60
redis-cli -h 43.143.122.92 -p 6379 -a '你的 Redis 密码' CONFIG REWRITE
```

含义：

- `timeout 0`：Redis 不主动断开空闲客户端。
- `tcp-keepalive 60`：帮助 Redis 更快发现异常断开的客户端。
- `CONFIG REWRITE`：把配置写回 redis.conf。

如果 Redis 在 Docker 中运行，进入容器后执行同样命令。如果云厂商安全组、负载均衡或代理层有 TCP idle timeout，也要调大到超过单个分析任务的最长运行时间。

## Milvus 数据查看

证据向量在 `evidence_extractor` 节点写入 Milvus，不是在 Firecrawl 搜索到网页时写入。

默认 collection：

```text
evidence_chunks
```

写入字段：

```text
id, task_id, chunk_id, competitor_name, source_type, source_url, embedding
```

可以用 Python 验证：

```powershell
cd backend
conda activate competitor-agent
python -c "from app.core.config import settings; from pymilvus import MilvusClient; c=MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token); print(c.list_collections()); print(c.get_collection_stats(settings.milvus_collection))"
```

如果要可视化查看 collection 数据，建议启动 Attu，并连接：

```text
Milvus Address: 43.143.122.92:19530
Database: default
Collection: evidence_chunks
```

Milvus 内置 WebUI 的 `data_component` 页面主要显示组件和运行状态，不是 collection 数据浏览页。

## 可选：不用 Celery 调试

如果只是临时调试，可以在 `backend/.env` 中设置：

```env
RUN_TASKS_INLINE=true
```

这种模式会在后端请求内直接执行完整 DAG，不推荐日常使用，因为真实采集和 LLM 分析可能超过前端 HTTP 超时时间。

## 常见问题

### 前端提示 API timeout

真实 Firecrawl、LLM、Milvus 流程会运行数分钟，不能用普通 HTTP 请求一直等待。应使用 Redis + Celery 异步执行，并在前端通过任务详情页轮询状态。

### 任务一直停在 queued

优先检查：

1. Celery Worker 是否启动。
2. Worker 是否监听 `competitor_agent_analysis` 队列。
3. Redis 是否可连接。
4. `competitor_agent:worker:heartbeat` 是否存在。

### Redis 出现 WinError 10054

这是远程 Redis 或中间网络重置 TCP 连接。当前代码已关闭 Redis ack emulation，并建议服务端设置 `timeout 0` 和 `tcp-keepalive 60`。

### Milvus WebUI 看不到数据

先用 pymilvus 查询 collection stats。如果 Python 能查到 `evidence_chunks` 和 `row_count`，说明数据已写入。内置 WebUI 的组件页不等于 collection 数据页，建议使用 Attu 查看。

## 当前能力边界

- 当前 DAG 是顺序执行，不是并行调度。
- Analyst Agent 当前按固定四个维度执行：功能、价格、市场、安全合规。
- Evidence Chunk 检索写入 Milvus，但当前分析阶段主要从 MySQL 按竞品读取 evidence，没有做复杂向量召回编排。
- 任务恢复逻辑适合本地开发和 MVP，生产环境建议进一步加入任务锁、幂等写入、死信队列和监控告警。
