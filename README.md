# Competitive Agent

AI 驱动的通用竞品分析 Agent 协作系统。项目目标是把“一句话竞品分析需求”拆解成可观测的多 Agent DAG 流程，并把任务、节点、日志、证据、结论、报告和 QA 结果落到 MySQL，前端通过 Vue 展示完整过程。

当前版本是可跑通的 MVP：

- 前端：Vue 3、Vite、TypeScript、Element Plus、VueFlow、Pinia、Axios、markdown-it
- 后端：FastAPI、Pydantic、SQLAlchemy、PyMySQL、Alembic、Celery
- 数据库：MySQL
- Agent 链路：Planner、Collector、Evidence Extractor、Feature/Pricing/Market/Security Analyst、Report Writer、QA
- 外部能力：已预留 Firecrawl、Milvus、LLM 工具层；当前 DAG 默认使用 mock 数据跑通端到端链路

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── agents/       # Agent 实现
│   │   ├── core/         # 配置、数据库、Celery
│   │   ├── graph/        # DAG 状态和执行流程
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic API Schema
│   │   ├── services/     # 业务服务
│   │   └── tools/        # Firecrawl / Milvus / LLM 工具层
│   ├── alembic/          # 数据库迁移
│   ├── requirements.txt
│   └── .env              # 本地环境变量，不提交
├── frontend/
│   ├── src/
│   │   ├── api/          # Axios API
│   │   ├── components/   # DAG、证据、报告等组件
│   │   ├── router/
│   │   ├── stores/
│   │   ├── types/
│   │   └── views/
│   └── package.json
└── competitive_agent_system_README.md
```

## 启动前准备

确认你已经完成：

1. Conda 环境已创建：`competitor-agent`
2. 后端依赖已安装：`backend/requirements.txt`
3. 前端依赖已安装：`frontend/package.json`
4. MySQL 已创建数据库：`competitor_agent`
5. `backend/.env` 已配置好数据库连接等环境变量

后端 `.env` 至少需要包含：

```env
DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/competitor_agent?charset=utf8mb4
CELERY_BROKER_URL=redis://:password@host:6379/0
CELERY_RESULT_BACKEND=redis://:password@host:6379/1
```

前端开发环境变量在 `frontend/.env.development`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## 初始化数据库

首次启动前，在项目根目录执行：

```powershell
cd backend
conda run -n competitor-agent python -m app.db_init
```

该命令会在 `competitor_agent` 数据库中创建以下核心表：

- `analysis_task`
- `agent_node`
- `agent_run_log`
- `source_document`
- `evidence_chunk`
- `claim`
- `claim_evidence`
- `report`
- `qa_result`

也可以使用 Alembic 迁移：

```powershell
cd backend
conda run -n competitor-agent alembic upgrade head
```

## 启动后端

在项目根目录执行：

```powershell
cd backend
conda run -n competitor-agent uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后可访问：

- 健康检查：http://127.0.0.1:8000/health
- API 文档：http://127.0.0.1:8000/docs

当前后端默认 `RUN_TASKS_INLINE=true`，创建分析任务后会在 FastAPI 请求中直接执行完整 DAG，方便本地演示，不强制启动 Celery Worker。

## 启动前端

另开一个终端，在项目根目录执行：

```powershell
cd frontend
npm run dev
```

启动后访问：

```text
http://127.0.0.1:5173/
```

## 使用流程

1. 打开前端首页。
2. 使用默认 Demo 输入文本，点击“解析需求”。
3. 检查或编辑高级配置。
4. 点击“开始分析”。
5. 进入任务详情页查看 DAG 节点和 Agent 日志。
6. 进入报告页查看 Markdown 报告、QA 结果和结构化 Claim。
7. 进入证据链页查看 Evidence Chunk 和来源信息。

## 可选：使用 Celery 后台执行

如果你希望任务通过 Celery Worker 执行：

1. 在 `backend/.env` 中加入：

```env
RUN_TASKS_INLINE=false
```

2. 启动后端：

```powershell
cd backend
conda run -n competitor-agent uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

3. 另开终端启动 Worker：

```powershell
cd backend
conda run -n competitor-agent celery -A app.worker worker --loglevel=info --pool=solo
```

Windows 本地建议使用 `--pool=solo`。

## 当前 MVP 说明

当前版本重点保证系统骨架和数据闭环完整：

- TaskPlan 解析可用
- 分析任务可创建
- DAG 节点状态和日志写入 MySQL
- Source Document、Evidence Chunk、Claim、Claim-Evidence 关联写入 MySQL
- Markdown 报告和 QA 结果可生成
- 前端可展示 DAG、日志、报告、证据链

真实外部采集和向量检索的接入点已经放在：

- `backend/app/tools/firecrawl_tool.py`
- `backend/app/tools/web_context_provider.py`
- `backend/app/tools/milvus_tool.py`
- `backend/app/tools/llm_client.py`

下一步可以把 `backend/app/graph/workflow.py` 中的 mock 采集和 mock 分析替换为真实 Firecrawl、LLM 和 Milvus 调用。
