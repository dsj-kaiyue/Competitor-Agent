# Competitive Agent

AI 驱动的通用竞品分析 Agent 协作系统。系统把用户的一句话竞品分析需求解析成结构化任务计划，然后通过多 Agent 协作完成资料采集、证据抽取、向量检索、结构化分析、报告生成、QA 复核和报告溯源。

这份 README 记录项目的真实系统形态，覆盖整体架构、Agent 协作方式、数据流、配置流程、数据库设计、运行方式和当前能力边界，适合拿去和 ChatGPT 继续讨论下一步行动方案。

## 系统能力概览

系统已经跑通真实主链路：

- Firecrawl：公开网页搜索和抓取。
- DeepSeek 兼容 OpenAI API：需求解析、Claim 生成、报告撰写、QA 复核。
- 阿里 DashScope `text-embedding-v4`：Evidence Chunk 向量化。
- Milvus：Evidence Chunk 向量存储与 RAG 检索。
- MySQL：任务、节点、日志、网页、证据、结论、报告、QA 结果的主存储。
- Redis + Celery：长任务异步执行。
- Vue 3 + VueFlow：前端展示任务 DAG、并行 worker、日志、证据链、报告、阶段耗时和历史任务。

核心能力：

- 资料采集 Agent 支持并行 Firecrawl search/scrape worker。
- 证据抽取 Agent 支持批量 embedding、批量 Milvus insert 和并行 embedding worker。
- 证据抽取阶段记录切块、MySQL、Embedding、Milvus 的阶段耗时。
- Analyst 执行层采用动态维度 Agent：`Dimension Prompt Planner Agent` 为每个分析维度生成 prompt spec，后端并行启动一个 `dimension_analysis_*` Agent 只分析该维度。
- 每个动态维度 Analyst 使用独立 DB Session、独立 EvidenceRetriever、独立 LLMClient 和独立 Milvus 查询上下文。
- DAG 页面可视化展示并行采集 worker、并行证据 worker、动态维度 Analyst 和 QA 回流边。
- Analyst Agent 使用 Milvus RAG 检索 evidence，Milvus 未命中时 fallback 到 MySQL evidence。
- ReportWriter 输出结构化 `report_json.sections`，报告段落可展开 Claim 和 Evidence。
- 报告页支持导出 Markdown 文件和 PDF 文件，并导出动态对比矩阵、QA 结果、结构化 Claim 和证据链。
- 任务控制支持暂停、恢复、取消和手动重试；Celery 不对业务失败自动反复 retry。
- 任务规划 Agent 在正式执行时只确认用户修改后的 TaskPlan，不二次 LLM 解析覆盖前端修改。
- 创建页的竞品列表和分析维度支持添加、编辑和删除。
- 创建页顶部提供“自动发现竞品”开关；只要打开，不管用户是否已输入竞品，解析阶段都会补充竞品并立即回填到前端供用户增删。
- 创建页顶部提供“自动添加分析维度”开关；只要打开，不管用户是否已输入分析维度，解析阶段都会补充推荐维度并立即回填到前端供用户增删。
- Planner Agent 根据用户输入场景动态推荐 `analysis_dimensions`，用户最终确认后的维度会生成动态画像 Schema。
- 系统生成动态竞品画像 `competitor_profile` 和动态对比矩阵 `comparison_matrix`，画像字段全部存储在 JSON 中，不增加行业固定列。
- ReportWriter 优先基于动态画像和动态矩阵组织报告，同时保留 Claim/Evidence 溯源。
- 报告接口返回动态画像和动态矩阵；报告页只展示“竞品动态对比矩阵”，避免把同一批画像信息重复显示两次。
- `/api/v1/analysis-tasks/{task_id}/metrics` 提供任务运行指标，任务详情页提供运行指标面板。
- 数据库新写入时间统一使用北京时间。
- QA 结果使用带 `next_action / target_nodes / revision_round` 的结构化 payload。
- QA 不通过时最多返工 1 轮，可回流到 collector、analyst 或 report_writer。
- 首页提供历史分析记录入口，历史页可查看以往任务、节点状态、报告和证据链。
- Planner fallback 根据用户输入推断目标产品、行业和竞品，不使用固定 AI 编程助手 demo 数据。

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
                          Claim -> CompetitorProfile -> ComparisonMatrix
                                      |
                                      v
                                  Report -> QA
```

核心设计原则：

- HTTP 请求只创建任务和查询状态，不阻塞等待完整分析。
- Celery Worker 执行真实长任务。
- MySQL 是最终业务数据来源。
- Redis 只做队列和运行态心跳。
- Milvus 只做向量检索，Evidence 原文仍以 MySQL 为准。
- 前端通过轮询任务、节点和日志接口展示动态执行过程。
- 分析维度由 Planner 推荐、用户最终确认，后端根据最终 `analysis_dimensions` 动态生成画像 Schema。
- 画像和矩阵用 JSON 保存，不把行业字段写死成数据库列。
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

这一节说明两件事：

1. 后端如何向 DeepSeek OpenAI 兼容 API 发送请求、接收返回、取出最终回答。
2. 当前系统中所有会调用 DeepSeek Chat API 的 Agent 分别使用什么 system prompt、user prompt、输入数据和输出数据。

### 统一调用入口

所有 DeepSeek Chat 请求都经过：

```text
backend/app/tools/llm_client.py
```

核心逻辑：

```python
model = ChatOpenAI(
    model=model_name,
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=90,
    temperature=0.2 if not settings.llm_thinking_enabled else None,
    **self._deepseek_thinking_kwargs(model_name),
)

messages = []
if system:
    messages.append(("system", system))
messages.append(("human", prompt))

return str(model.invoke(messages).content)
```

系统不会在各个 Agent 中手写 HTTP 请求体，而是使用 `langchain_openai.ChatOpenAI` 调用 DeepSeek 的 OpenAI 兼容接口。也就是说，所有 Agent 最终都走同一套 `LLMClient.complete(prompt, system=...)`。

### 请求地址

`.env` 中的关键配置：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_THINKING_ENABLED=false
LLM_REASONING_EFFORT=high
```

因为 DeepSeek 使用 OpenAI 兼容 Chat Completions 协议，实际请求地址等价于：

```http
POST https://api.deepseek.com/v1/chat/completions
```

`LLM_BASE_URL` 只配置到 `/v1`，SDK 会自动拼接 `/chat/completions`。

### 统一请求体结构

关闭思考模式时，请求体等价于：

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
  ],
  "thinking": {
    "type": "disabled"
  }
}
```

开启思考模式时，请求体等价于：

```json
{
  "model": "deepseek-v4-pro",
  "messages": [
    {
      "role": "system",
      "content": "系统提示词"
    },
    {
      "role": "user",
      "content": "用户提示词"
    }
  ],
  "thinking": {
    "type": "enabled"
  },
  "reasoning_effort": "high"
}
```

说明：

- `timeout=90` 是 SDK 客户端超时配置，不是请求体字段。
- `temperature=0.2` 只在 `LLM_THINKING_ENABLED=false` 时传入。
- `thinking` 来自 `ChatOpenAI(..., extra_body={"thinking": {"type": "..."} })`，最终作为 DeepSeek 扩展字段传给 API。
- `reasoning_effort` 只在 `LLM_THINKING_ENABLED=true` 且 `LLM_REASONING_EFFORT` 有值时传入。

### 返回数据结构与系统实际取值

DeepSeek Chat Completions 返回结构等价于：

```json
{
  "id": "chatcmpl_xxx",
  "object": "chat.completion",
  "created": 1770000000,
  "model": "deepseek-v4-pro",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"passed\":true,\"score\":0.91,\"issues\":[]}",
        "reasoning_content": "这里可能是思考内容，仅开启思考模式时存在"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "total_tokens": 1200
  }
}
```

当前系统只读取：

```text
response.choices[0].message.content
```

在代码里对应：

```python
model.invoke(messages).content
```

系统不会读取、保存、解析或使用：

```text
response.choices[0].message.reasoning_content
```

因此，即使开启 DeepSeek 思考模式，业务逻辑也只会处理最终回答 `content`，不会把思考内容写入 MySQL、报告、Agent 日志或 Claim。

### JSON 解析规则

多数 Agent 都要求 DeepSeek 只输出 JSON。后端统一通过 `_json_from_text()` 解析：

~~~text
1. 如果 content 中存在 ```json fenced block，先取 fenced block 内文本。
2. 优先直接 json.loads(content)。
3. 如果直接解析失败，再用正则提取最外层 JSON 对象或数组。
~~~

动态维度 Analyst 还额外使用 `_parse_llm_json_with_repair()`。如果第一次返回不是合法 JSON，系统会再调用一次 DeepSeek，让模型把上一次输出修正为合法 JSON。

JSON 修正请求的 system prompt：

```text
你只输出合法 JSON。
```

JSON 修正请求的 user prompt：

```text
上一次模型输出不是合法 JSON，解析失败：{first_exc}

请把下面内容修正为合法 JSON。
要求：
1. 只输出合法 JSON，不要 Markdown，不要解释。
2. 期望 JSON 类型：{expected}
3. 如果原内容为空或无法修复，请基于原始任务 prompt 输出一个空 JSON 数组 []。

原始任务 prompt：
{original_prompt[-5000:]}

上一次模型输出：
{raw[:5000]}
```

修正请求的输出仍然只取 `content` 并执行 JSON 解析。

### 调用 DeepSeek 的 Agent 总览

| Agent / 步骤 | 触发时机 | 输入 | 输出 | 是否写库 |
| --- | --- | --- | --- | --- |
| Planner Agent | 前端点击“解析需求” | 用户原始需求、自动发现开关、自动添加维度开关 | `TaskPlan` | 不直接写任务表，接口返回前端 |
| Dimension Suggestion Agent | 解析需求阶段，且自动添加分析维度开启 | 用户需求、当前 `TaskPlan`、已有维度 | 新增分析维度数组 | 合并到返回前端的 `TaskPlan` |
| Competitor Discovery Agent | 解析需求阶段自动发现竞品；正式执行阶段只做兜底 | `TaskPlan`、Firecrawl search 结果 | 新增竞品数组 | 解析阶段返回前端；正式执行阶段更新 `task_plan_json` |
| Dimension Prompt Planner Agent | 正式执行阶段，Planner 节点确认后 | `TaskPlan`、动态画像字段 schema | 每个维度的 prompt spec | 写入对应 `agent_node.input_summary/output_summary` 和运行态 spec |
| Dynamic Dimension Analyst Agent | 证据抽取完成后 | 某个维度的 prompt spec、某个竞品、RAG evidence | Claim JSON 数组 | 写入 `claim`、`claim_evidence` |
| ReportWriter Agent | 动态维度 Analyst 完成且至少有 Claim | 画像、矩阵、Claim | 报告 JSON | 写入 `report` |
| QA Agent | ReportWriter 完成后 | 报告 Markdown、本地规则检查问题 | QA 结果 JSON | 写入 `qa_result` |

### 1. Planner Agent：需求解析

代码位置：

```text
backend/app/agents/planner_agent.py
```

触发接口：

```http
POST /api/v1/task-plans/parse
```

前端请求示例：

```json
{
  "user_input": "请分析 Firecrawl 在 AI 数据采集领域的竞品情况，重点关注网页抓取能力、结构化抽取能力和开发者生态。",
  "auto_discover_competitors": true,
  "auto_add_analysis_dimensions": true
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
你是竞品分析 Planner Agent。请把用户输入解析成通用竞品分析 TaskPlan。
你需要根据用户输入判断本次竞品分析场景，并推荐适合该场景的分析维度。

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
  "data_sources": ["official_website","pricing_page","docs","blog","news","reviews"],
  "template_key": "string or null"
}

规则：
- 如果用户只给了目标产品和行业，没有明确列出竞品，competitors 输出空数组，并把 auto_discover_competitors 设为 true。
- 不要使用示例产品或默认竞品填充结果。
- topic、industry、target_product 必须忠实来自用户输入。
- analysis_dimensions 必须根据行业和用户场景动态生成，不能固定返回 AI 编程助手维度。
- 如果用户明确写了“重点关注 xxx”，必须优先保留这些维度。
- 如果用户没有指定维度，根据行业自动推荐 5 到 8 个中文短语维度，适合直接展示给用户编辑。
- AI 数据采集场景可包含“数据采集能力”“网页抓取能力”“结构化抽取能力”“开发者生态”等；AI 搜索场景可包含“搜索能力”“引用质量”“研究报告能力”等；新能源汽车场景可包含“车型定位”“续航能力”“智能驾驶”等。
```

发送给 DeepSeek 的 messages 示例：

```json
[
  {
    "role": "system",
    "content": "你只输出合法 JSON。"
  },
  {
    "role": "user",
    "content": "你是竞品分析 Planner Agent。请把用户输入解析成通用竞品分析 TaskPlan。\n你需要根据用户输入判断本次竞品分析场景，并推荐适合该场景的分析维度。\n\n用户输入：\n请分析 Firecrawl 在 AI 数据采集领域的竞品情况，重点关注网页抓取能力、结构化抽取能力和开发者生态。\n\n只输出 JSON，不要输出解释。格式：..."
  }
]
```

DeepSeek `content` 期望示例：

```json
{
  "topic": "Firecrawl 在 AI 数据采集领域的竞品分析",
  "industry": "AI 数据采集",
  "target_product": "Firecrawl",
  "competitors": [],
  "analysis_dimensions": ["网页抓取能力", "结构化抽取能力", "开发者生态", "价格策略", "安全合规", "性能与延迟表现"],
  "report_depth": "standard",
  "output_language": "zh-CN",
  "auto_discover_competitors": true,
  "data_sources": ["official_website", "pricing_page", "docs", "blog", "news", "reviews"],
  "template_key": null
}
```

系统取值：

```text
content -> JSON object -> TaskPlan(**data)
```

使用字段：

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
template_key
```

输出给前端的结构：

```json
{
  "task_plan": {
    "topic": "Firecrawl 在 AI 数据采集领域的竞品分析",
    "industry": "AI 数据采集",
    "target_product": "Firecrawl",
    "competitors": ["Apify", "Bright Data", "Diffbot"],
    "analysis_dimensions": ["网页抓取能力", "结构化抽取能力", "开发者生态", "价格策略", "安全合规", "性能与延迟表现"],
    "report_depth": "standard",
    "output_language": "zh-CN",
    "auto_discover_competitors": true,
    "data_sources": ["official_website", "pricing_page", "docs", "blog", "news", "reviews"],
    "template_key": null
  }
}
```

补充规则：

- 如果 DeepSeek 调用失败或 JSON 解析失败，后端会使用 `_infer_task_plan()` 做本地兜底。
- 如果 `auto_discover_competitors=true`，Planner 解析后会继续执行 Competitor Discovery Agent，并把新增竞品合并进 `competitors`。
- 如果 `auto_add_analysis_dimensions=true`，Planner 解析后会继续执行 Dimension Suggestion Agent，并把新增维度合并进 `analysis_dimensions`。
- 点击“开始分析”后的正式 `planner` 节点不再调用 DeepSeek，只确认前端最终编辑后的 TaskPlan。

### 2. Dimension Suggestion Agent：自动添加分析维度

代码位置：

```text
backend/app/agents/planner_agent.py
```

触发时机：

```text
POST /api/v1/task-plans/parse
且请求体 auto_add_analysis_dimensions=true
```

输入示例：

```json
{
  "user_input": "请分析 Firecrawl 在 AI 数据采集领域的竞品情况。",
  "current_plan": {
    "topic": "Firecrawl 竞品分析",
    "industry": "AI 数据采集",
    "target_product": "Firecrawl",
    "analysis_dimensions": ["价格策略", "安全合规"]
  }
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请根据用户输入和当前 TaskPlan，补充推荐一些更适合本次竞品分析的分析维度。

用户输入：
{user_input}

当前主题：{plan.topic}
行业：{plan.industry}
目标产品：{plan.target_product}
已有分析维度：{json.dumps(existing, ensure_ascii=False)}

要求：
- 只输出 JSON 数组，最多 {max_dimensions} 个中文短语。
- 不要重复已有分析维度。
- 不要固定套用 AI 编程助手维度。
- 如果场景是 AI 数据采集，可以补充“网页抓取能力”“结构化抽取能力”“开发者生态”等。
- 如果场景是 AI 搜索，可以补充“搜索能力”“引用质量”“研究报告能力”等。
- 如果用户输入中有“重点关注”，优先围绕这些重点补充。
```

DeepSeek `content` 期望示例：

```json
["网页抓取能力", "结构化抽取能力", "开发者生态", "反爬与稳定性"]
```

也兼容对象格式：

```json
{
  "analysis_dimensions": ["网页抓取能力", "结构化抽取能力", "开发者生态"]
}
```

系统取值：

```text
content -> JSON array
```

如果返回对象，则取：

```text
analysis_dimensions
```

合并规则：

```text
1. 保留用户已有维度。
2. 过滤空字符串。
3. 按名称去重。
4. 最多追加 max_dimensions 个新维度。
5. 返回前端后允许用户继续增加或删除。
```

### 3. Competitor Discovery Agent：自动发现竞品

代码位置：

```text
backend/app/agents/planner_agent.py
backend/app/graph/workflow.py
```

触发时机：

```text
解析需求阶段：
POST /api/v1/task-plans/parse
且请求体 auto_discover_competitors=true

正式分析阶段：
仅作为兜底逻辑，当 TaskPlan.auto_discover_competitors=true 且 competitors 仍为空时触发
```

输入由两部分组成：

```json
{
  "target": "Firecrawl",
  "industry": "AI 数据采集",
  "firecrawl_search_results": [
    {
      "title": "Apify - Web Scraping and Automation Platform",
      "url": "https://apify.com/",
      "description": "Cloud platform for web scraping, crawling and browser automation."
    },
    {
      "title": "Bright Data Web Scraper APIs",
      "url": "https://brightdata.com/",
      "description": "Data collection infrastructure and web scraping APIs."
    }
  ]
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请从搜索结果中识别与目标产品最相关的直接竞品或替代产品。
目标产品：{target}
行业：{plan.industry}
搜索结果：
{discovery_context}

只输出 JSON 数组，最多 {max_competitors} 个产品名。不要包含目标产品本身，不要输出解释。
```

其中 `discovery_context` 形如：

```text
- title=Apify - Web Scraping and Automation Platform; url=https://apify.com/; description=Cloud platform for web scraping, crawling and browser automation.
- title=Bright Data Web Scraper APIs; url=https://brightdata.com/; description=Data collection infrastructure and web scraping APIs.
```

DeepSeek `content` 期望示例：

```json
["Apify", "Bright Data", "Diffbot", "Browse AI"]
```

也兼容对象格式：

```json
{
  "competitors": ["Apify", "Bright Data", "Diffbot", "Browse AI"]
}
```

系统取值：

```text
content -> JSON array
```

如果返回对象，则取：

```text
competitors
```

合并规则：

```text
1. 保留用户已有 competitors。
2. 过滤空字符串。
3. 过滤目标产品自身。
4. 按名称去重。
5. 最多保留 6 个自动发现竞品。
6. 返回前端后允许用户继续增加或删除。
```

正式执行阶段的兜底规则：

- 如果正式任务开始时 `competitors` 仍为空，且 `auto_discover_competitors=true`，Collector 会再次调用该能力。
- 如果仍然没有发现任何竞品，任务会失败并提示 `Auto competitor discovery did not produce competitors`。

### 4. Dimension Prompt Planner Agent：为每个维度生成专属 prompt spec

代码位置：

```text
backend/app/graph/workflow.py
backend/app/services/task_service.py
```

触发时机：

```text
正式分析任务开始后，planner 节点确认 TaskPlan 之后
```

输入示例：

```json
{
  "topic": "Firecrawl 在 AI 数据采集领域的竞品分析",
  "industry": "AI 数据采集",
  "target_product": "Firecrawl",
  "competitors": ["Apify", "Bright Data", "Diffbot"],
  "fields": [
    {
      "key": "web_crawling_capability",
      "label": "网页抓取能力",
      "value_type": "text"
    },
    {
      "key": "structured_extraction_capability",
      "label": "结构化抽取能力",
      "value_type": "text"
    }
  ]
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
你是 Dimension Prompt Planner Agent。请为每一个分析维度生成专属 prompt spec，供后续独立维度分析 Agent 使用。

任务主题：{plan.topic}
行业：{plan.industry}
目标产品：{plan.target_product}
竞品：{', '.join(plan.competitors)}
动态维度字段：
{json.dumps(fields, ensure_ascii=False)}

要求：
1. 必须为每个字段输出一条 spec，不能新增或删除维度。
2. dimension_key 必须等于字段 key，dimension_label 必须等于字段 label。
3. analysis_goal、must_answer、evidence_focus、comparison_criteria 必须适配该维度和行业。
4. 不要输出完整报告，不要执行分析。
5. 只输出合法 JSON 数组。

格式：
[
  {"dimension_key":"...","dimension_label":"...","analysis_goal":"...","evidence_focus":["official docs"],"must_answer":["..."],"comparison_criteria":["..."]}
]
```

DeepSeek `content` 期望示例：

```json
[
  {
    "dimension_key": "web_crawling_capability",
    "dimension_label": "网页抓取能力",
    "analysis_goal": "比较各竞品在网页抓取、爬取深度、动态页面处理和抓取稳定性上的能力。",
    "evidence_focus": ["official_website", "docs", "blog"],
    "must_answer": ["是否支持动态页面抓取", "是否提供 API/SDK", "是否说明并发、限流或失败重试能力"],
    "comparison_criteria": ["抓取范围", "动态页面支持", "开发者集成", "稳定性"]
  },
  {
    "dimension_key": "structured_extraction_capability",
    "dimension_label": "结构化抽取能力",
    "analysis_goal": "比较各竞品将网页内容转化为结构化数据、Markdown 或 LLM 可用数据的能力。",
    "evidence_focus": ["docs", "official_website"],
    "must_answer": ["支持哪些输出格式", "是否支持 schema 或字段级抽取", "是否有官方示例"],
    "comparison_criteria": ["输出格式", "schema 支持", "抽取准确性", "LLM 适配"]
  }
]
```

系统取值：

```text
content -> JSON array
```

如果返回对象，则取：

```text
dimensions
```

每条 spec 使用字段：

```text
dimension_key
dimension_label
analysis_goal
evidence_focus
must_answer
comparison_criteria
```

容错规则：

- 系统会先为每个维度生成本地 fallback spec。
- 如果 DeepSeek 返回合法 spec，则用 DeepSeek spec 覆盖对应维度的 fallback spec。
- 如果 DeepSeek 调用失败或返回不合法，系统使用 fallback spec，不会阻塞整个任务。

### 5. Dynamic Dimension Analyst Agent：每个分析维度一个动态 Agent

代码位置：

```text
backend/app/graph/workflow.py
```

触发时机：

```text
资料采集完成
-> 证据抽取完成
-> Dimension Prompt Planner 已经生成 prompt spec
-> 并行执行 N 个 dimension_analysis_* Agent
```

执行模型：

```text
TaskPlan.analysis_dimensions
  -> Dimension Prompt Planner Agent
  -> N 个 prompt spec
  -> N 个 Dynamic Dimension Analyst Agent
  -> 每个 Agent 只分析一个维度
  -> 每个 Agent 内部会遍历所有竞品
```

输入示例：

```json
{
  "dimension_prompt_spec": {
    "dimension_key": "structured_extraction_capability",
    "dimension_label": "结构化抽取能力",
    "analysis_goal": "比较各竞品将网页内容转化为结构化数据、Markdown 或 LLM 可用数据的能力。",
    "must_answer": ["支持哪些输出格式", "是否支持 schema 或字段级抽取", "是否有官方示例"],
    "comparison_criteria": ["输出格式", "schema 支持", "抽取准确性", "LLM 适配"]
  },
  "competitor": "Apify",
  "topic": "Firecrawl 在 AI 数据采集领域的竞品分析",
  "evidence": [
    {
      "evidence_id": 101,
      "competitor": "Apify",
      "source_type": "docs",
      "title": "Apify Documentation",
      "url": "https://docs.apify.com/",
      "text": "Apify Actors can crawl websites and extract structured data..."
    }
  ]
}
```

System prompt：

```text
你只输出合法 JSON，不编造证据。
```

User prompt 模板：

```text
你是一个动态维度竞品分析 Agent。你只负责一个分析维度，不要分析其它维度。
当前维度 key：{dimension_key}
当前维度名称：{dimension_label}
分析目标：{analysis_goal}
比较标准：{criteria}
必须回答：
{must_answer}

竞品：{competitor}
分析主题：{plan.topic}
证据：
{_evidence_context(evidence, limit=12)}

输出 JSON 数组，最多 3 条。每条格式：
{"competitor_name":"{competitor}","dimension_key":"{dimension_key}","dimension_label":"{dimension_label}","claim_text":"中文结论，必须具体且可被证据支撑","evidence_ids":[数字ID],"confidence":0.0到1.0,"risk_level":"low|medium|high"}
不要输出 JSON 之外的内容。
```

其中 evidence context 形如：

```text
[evidence_id=101] competitor=Apify; source_type=docs; title=Apify Documentation; url=https://docs.apify.com/; text=Apify Actors can crawl websites and extract structured data...
[evidence_id=102] competitor=Apify; source_type=official_website; title=Apify Web Scraping; url=https://apify.com/web-scraping; text=...
```

DeepSeek `content` 期望示例：

```json
[
  {
    "competitor_name": "Apify",
    "dimension_key": "structured_extraction_capability",
    "dimension_label": "结构化抽取能力",
    "claim_text": "Apify 通过 Actors 和数据集机制支持从网页抓取流程中产出结构化数据，适合需要自定义抓取逻辑的开发者场景。",
    "evidence_ids": [101, 102],
    "confidence": 0.86,
    "risk_level": "low"
  },
  {
    "competitor_name": "Apify",
    "dimension_key": "structured_extraction_capability",
    "dimension_label": "结构化抽取能力",
    "claim_text": "Apify 的结构化抽取能力更偏工作流和 Actor 编排，是否开箱即用地输出 LLM 友好 Markdown 需要结合具体 Actor 或模板判断。",
    "evidence_ids": [101],
    "confidence": 0.72,
    "risk_level": "medium"
  }
]
```

也兼容对象格式：

```json
{
  "claims": [
    {
      "claim_text": "Apify 支持通过 Actors 抓取网页并输出结构化数据。",
      "evidence_ids": [101],
      "confidence": 0.8,
      "risk_level": "low"
    }
  ]
}
```

系统取值：

```text
content -> JSON array
```

如果返回对象，则取：

```text
claims
```

每条 Claim 使用字段：

```text
competitor_name
claim_text
evidence_ids
confidence
risk_level
```

写入 MySQL：

```text
claim.task_id
claim.agent_node_id
claim.competitor_name
claim.claim_type = "dimension"
claim.dimension_key
claim.dimension_label
claim.dimension_prompt_json
claim.claim_text
claim.confidence
claim.risk_level
claim_evidence.claim_id
claim_evidence.evidence_chunk_id
```

系统会强制使用当前 Agent 的维度：

```text
dimension_key = 当前 prompt spec 的 dimension_key
dimension_label = 当前 prompt spec 的 dimension_label
```

即使模型返回了错误维度，写库时也以当前 Agent 上下文为准。

证据绑定规则：

```text
1. evidence_ids 只能引用本次传给 DeepSeek 的 evidence_id。
2. 如果模型返回了不存在的 evidence_id，会被过滤。
3. 如果模型没有返回有效 evidence_ids，但本次 RAG 有 evidence，系统默认绑定第一条 evidence。
4. 每条 Claim 最多绑定 4 条 evidence。
5. 每个竞品在每个维度下最多保留 3 条 Claim。
```

失败与跳过规则：

- 如果某个竞品没有检索到任何 evidence，该竞品会被跳过并记录 warning。
- 只有当某个维度对所有竞品都没有 evidence 时，该维度 Agent 才允许跳过。
- 如果已有 evidence，但 DeepSeek 返回非 JSON、非数组、空数组、空 `claim_text`、请求失败、余额不足或超时，该维度 Agent 会失败。
- 只要有一个维度 Agent 因真实异常失败，整个 workflow 会停在分析阶段，不会继续生成空报告。
- 如果所有动态维度 Agent 都没有生成 Claim，ReportWriter 之前会失败。

### 6. ReportWriter Agent：生成报告 JSON

代码位置：

```text
backend/app/graph/workflow.py
```

触发时机：

```text
所有动态维度 Analyst 完成
且至少生成 1 条 Claim
```

输入示例：

```json
{
  "topic": "Firecrawl 在 AI 数据采集领域的竞品分析",
  "industry": "AI 数据采集",
  "competitors": ["Apify", "Bright Data", "Diffbot"],
  "analysis_dimensions": ["网页抓取能力", "结构化抽取能力", "开发者生态"],
  "competitor_profiles": [
    {
      "competitor_name": "Apify",
      "dynamic_profile_json": {
        "structured_extraction_capability": "通过 Actors 和数据集产出结构化数据"
      }
    }
  ],
  "comparison_matrices": [
    {
      "dimension_key": "structured_extraction_capability",
      "matrix_json": {
        "rows": [
          {
            "competitor_name": "Apify",
            "value": "支持自定义抓取和结构化输出"
          }
        ]
      }
    }
  ],
  "claims": [
    {
      "claim_id": 1,
      "competitor": "Apify",
      "dimension": "结构化抽取能力",
      "evidence_ids": [101, 102],
      "text": "Apify 通过 Actors 和数据集机制支持结构化数据产出。"
    }
  ]
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请基于动态竞品画像、对比矩阵和结构化 Claim 生成中文竞品分析报告 JSON。
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
7. 优先基于 CompetitorProfiles 和 ComparisonMatrices 组织内容，但关键段落仍要引用 claim_ids。

JSON 格式：
{"title":"...","sections":[{"section_id":"executive_summary","title":"执行摘要","paragraphs":[{"paragraph_id":"executive_summary_p1","text":"...","claim_ids":[1,2]}]}]}

CompetitorProfiles:
{profile_context}

ComparisonMatrices:
{matrix_context}

Claims:
{claim_context}
```

`claim_context` 示例：

```text
[claim_id=1] competitor=Apify; dimension=结构化抽取能力; evidence_ids=[101, 102]; text=Apify 通过 Actors 和数据集机制支持结构化数据产出。
[claim_id=2] competitor=Bright Data; dimension=网页抓取能力; evidence_ids=[120]; text=Bright Data 提供面向企业的数据采集基础设施和代理网络。
```

DeepSeek `content` 期望示例：

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
          "text": "Firecrawl 的主要竞品覆盖开发者抓取平台、企业级数据采集基础设施和网页结构化抽取服务三类。",
          "claim_ids": [1, 2]
        }
      ]
    },
    {
      "section_id": "structured_extraction_capability",
      "title": "结构化抽取能力",
      "paragraphs": [
        {
          "paragraph_id": "structured_extraction_capability_p1",
          "text": "Apify 更强调通过 Actors 构建抓取流程并输出结构化数据，适合需要高度自定义的场景。",
          "claim_ids": [1]
        }
      ]
    }
  ]
}
```

系统取值：

```text
content -> JSON object
```

使用字段：

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

后端自动补充：

```text
paragraphs[].evidence_ids
report_json.mode = "firecrawl_llm_milvus_rag"
```

写入 MySQL：

```text
report.title
report.report_json
report.content_markdown
report.content_html
```

容错规则：

- 如果没有任何 Claim，ReportWriter 不会调用 DeepSeek，会直接失败，避免生成空报告。
- 如果有 Claim，但 DeepSeek 报告 JSON 不合法或缺少 `sections`，后端会使用 `_fallback_report_json()` 基于 Claim 生成基础报告。

### 7. QA Agent：报告复核

代码位置：

```text
backend/app/graph/workflow.py
```

触发时机：

```text
ReportWriter 完成后
```

QA 分两步：

```text
1. 后端先做本地规则检查，例如是否有报告、是否有 Claim、段落是否绑定 claim_ids 等。
2. 再把报告 Markdown 和本地规则问题交给 DeepSeek 复核。
```

输入示例：

```json
{
  "report_markdown": "# Firecrawl 在 AI 数据采集领域的竞品分析报告\n\n## 执行摘要\n...",
  "local_rule_issues": [
    {
      "type": "weak_evidence",
      "severity": "medium",
      "message": "部分段落引用的 Claim 数量较少",
      "related_claim_id": null,
      "suggested_action": "rewrite"
    }
  ]
}
```

System prompt：

```text
你只输出合法 JSON。
```

User prompt 模板：

```text
请复核这份竞品分析报告是否存在明显逻辑或证据问题。
仅基于报告和问题列表输出 JSON：
{"passed":true/false,"score":0.0到1.0,"issues":[{"type":"logic_gap|unsupported_claim|weak_evidence|schema_incomplete|writing_issue","severity":"low|medium|high","message":"中文问题","related_claim_id":null,"related_dimension":"动态维度名称","suggested_action":"recollect|reanalyze|rewrite|ignore","target_node":null}]}

报告：
{report.content_markdown[:6000]}

规则检查问题：
{json.dumps(issues, ensure_ascii=False)}
```

DeepSeek `content` 期望示例：

```json
{
  "passed": false,
  "score": 0.72,
  "issues": [
    {
      "type": "weak_evidence",
      "severity": "medium",
      "message": "价格策略部分缺少官方价格页证据，建议补采价格页后重跑相关维度分析。",
      "related_claim_id": 12,
      "related_dimension": "价格策略",
      "suggested_action": "recollect",
      "target_node": "collector"
    }
  ]
}
```

系统取值：

```text
content -> JSON object
```

使用字段：

```text
passed
score
issues
```

写入 MySQL：

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
  "revision_reason": "价格策略证据较弱，需要补采官方价格页。",
  "followup_queries": ["Apify pricing official", "Bright Data pricing official"],
  "revision_round": 0
}
```

容错规则：

- 如果 QA LLM 调用失败，后端会使用本地规则检查结果兜底。
- QA 只处理已经进入报告阶段的结果。
- 如果动态维度 Analyst 阶段因为 DeepSeek 失败、余额不足、超时或 JSON 不合法而失败，workflow 会停在分析阶段，不会交给 QA 吞掉。

### 不调用 DeepSeek Chat API 的 Agent 或步骤

以下步骤不向 DeepSeek Chat API 发送请求：

- 正式执行中的 `planner` 节点：只确认前端最终编辑的 TaskPlan，不再二次解析。
- `collector` 的普通资料采集：调用 Firecrawl search/scrape，不调用 DeepSeek；只有自动发现竞品时才调用 DeepSeek。
- `collector_worker_*`：并行执行 Firecrawl 采集，不调用 DeepSeek。
- `evidence_extractor`：做文本切块、批量 embedding、批量写 Milvus，不调用 DeepSeek Chat。
- `evidence_worker_*`：并行处理证据抽取，不调用 DeepSeek Chat。
- `EvidenceRetriever.search()`：调用 DashScope embedding 生成 query vector，然后查 Milvus，不调用 DeepSeek Chat。
- 报告导出：从 MySQL 读取报告、矩阵、QA、Claim 和证据链，生成 Markdown 或 PDF，不调用 DeepSeek。

DashScope embedding 请求地址来自：

```env
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
```

实际等价于：

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
```

embedding 返回只取：

```text
response.data[].embedding
```

这些向量用于写入 Milvus 或做 RAG 检索，不会进入 DeepSeek 的 `reasoning_content`。

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

系统会为每个分析任务创建基础 Agent 节点，并根据用户最终确认的 `analysis_dimensions` 动态创建 N 个维度分析节点。节点定义在 `backend/app/services/task_service.py`，执行逻辑在 `backend/app/graph/workflow.py`。

| node_key | Agent | 职责 | 主要输出 |
| --- | --- | --- | --- |
| `planner` | 任务规划 Agent | 将用户自然语言解析为 TaskPlan；必要时自动发现竞品 | `task_plan_json` |
| `dimension_planner` | 维度 Prompt Planner Agent | 为每个分析维度生成专属 prompt spec | `agent_node.input_summary` / 运行态 prompt spec |
| `collector` | 资料采集 Agent | 生成搜索 query，调用 Firecrawl search/scrape | `source_document` |
| `evidence_extractor` | 证据抽取 Agent | 清洗网页、切 chunk、embedding、写 Milvus | `evidence_chunk` |
| `dimension_analysis_*` | 动态维度分析 Agent | 每个节点只负责一个分析维度，基于 RAG evidence 生成带 `dimension_key / dimension_label` 的 Claim | `claim` |
| `report_writer` | 报告撰写 Agent | 基于 Claim 生成结构化报告 JSON 和 Markdown | `report` |
| `qa` | QA Agent | 规则检查 + LLM 复核，必要时触发一次返工 | `qa_result` |

### 逻辑 DAG

```text
planner
  |
dimension_planner
  |
collector
  |
evidence_extractor
  |---------------- dimension_analysis_维度1
  |---------------- dimension_analysis_维度2
  |---------------- dimension_analysis_维度3
  |---------------- ...
                           |
                    report_writer
                           |
                          qa
```

前端会把动态维度 Analyst 显示为并行分支；后端也会使用独立线程并行执行这些维度 Analyst。每个维度 Analyst 都会创建独立 SQLAlchemy Session、独立 EvidenceRetriever 和独立 LLMClient，避免跨线程共享 DB Session。

### 运行时并行 worker 可视化

系统提供两类虚拟 worker：

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

行为说明：

- LLM 解析失败时，fallback 会根据用户输入推断目标产品和行业，不使用固定 Cursor / Copilot / Windsurf / Tabnine demo 数据。
- 创建页顶部有“自动发现竞品”和“自动添加分析维度”两个开关，默认打开。
- 只要解析请求中的 `auto_discover_competitors=true`，后端就会额外执行竞品发现，并把发现结果追加到 `competitors` 返回前端；即使用户原始输入里已经写了竞品，也会继续补充。
- 只要解析请求中的 `auto_add_analysis_dimensions=true`，后端会在 Planner 原始维度基础上再调用 Agent 推荐增量维度，并合并去重返回前端；即使用户原始输入里已经写了重点维度，也会继续补充适合场景的新维度。
- 如果用户关闭“自动发现竞品”，后端只做需求解析，不额外搜索补充竞品。
- 如果用户关闭“自动添加分析维度”，后端只使用 Planner 解析出的维度，不额外补充维度。
- 如果解析后在顶部把“自动发现竞品”从关闭切换为开启，前端会再次请求解析与自动发现，但只合并新增竞品，不覆盖用户已经编辑过的主题、维度、语言等其它 TaskPlan 字段。
- 如果解析后在顶部把“自动添加分析维度”从关闭切换为开启，前端会再次请求维度推荐，但只合并新增分析维度，不覆盖用户已经编辑过的主题、竞品、语言等其它 TaskPlan 字段。
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
- 基础 `agent_node`
- N 条动态 `dimension_analysis_*` 节点，数量由用户最终确认的 `analysis_dimensions` 决定

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

分析阶段采用并行执行：

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

相关服务：

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

Claim 现在由动态维度 Analyst 生成，而不是由四个固定 Analyst 生成。每个维度 Analyst 的 query 会基于：

- 竞品名称。
- 当前 `dimension_label`。
- Dimension Prompt Planner 生成的 `evidence_focus`。
- 任务主题 `topic`。

如果维度或 `evidence_focus` 中包含 `pricing / 价格 / billing` 等价格信号，RAG 检索会优先尝试 `pricing_page` 来源；其它维度默认使用 Milvus RAG 检索，不强制来源类型。

执行方式：

- N 个动态维度 Analyst 在后端使用 `ThreadPoolExecutor` 真正并行执行。
- 每个维度 Analyst 线程独立创建 SQLAlchemy `SessionLocal()`。
- 每个维度 Analyst 独立创建 `EvidenceRetriever`、`LLMClient` 和 Milvus 查询上下文。
- 主线程收集各维度 Analyst 生成的 claim id，并等待全部维度 Analyst 完成后再进入动态画像、矩阵和 `report_writer`。
- 如果任一维度 Analyst 因 LLM 调用失败、JSON 无法修复、DB/Milvus 异常、或“已有 evidence 但没有生成 Claim”而失败，主 workflow 会立即停止，任务进入失败状态，避免继续生成空报告。
- 只有当某个维度对所有竞品都没有检索到 evidence 时，该维度才允许被跳过；如果最终所有维度都没有 Claim，ReportWriter 不会执行。
- QA 返工时，如果目标是多个维度 Analyst，也会并行重跑目标维度；如果 QA 没给出具体目标，会重跑全部动态维度 Analyst。

LLM 输出 Claim JSON：

```json
[
  {
    "competitor_name": "Firecrawl",
    "dimension_key": "structured_extraction_capabilities",
    "dimension_label": "结构化抽取能力",
    "claim_text": "中文结论",
    "evidence_ids": [101, 102],
    "confidence": 0.86,
    "risk_level": "low"
  }
]
```

如果 LLM 没返回 `evidence_ids`，系统默认绑定本次 RAG 检索的 top evidence。

Claim 只允许绑定本次传给 LLM 的 evidence，避免把全量 evidence 都挂上去。

### 7. 动态竞品画像与动态对比矩阵

动态维度 Analyst 完成后，ReportWriter 之前，workflow 会执行动态知识构建：

```text
task_plan_json.analysis_dimensions
  -> ProfileSchemaBuilder
  -> competitor_profile.profile_schema_json
  -> competitor_profile.profile_data_json
  -> comparison_matrix.matrix_schema_json / matrix_data_json
```

相关后端文件：

```text
backend/app/services/profile_schema_builder.py
backend/app/services/competitor_profile_service.py
backend/app/services/comparison_matrix_service.py
backend/app/models/competitor_profile.py
backend/app/models/comparison_matrix.py
```

`ProfileSchemaBuilder` 会把用户最终确认的 `analysis_dimensions` 转成动态字段：

```json
{
  "template_key": "web_data_collection",
  "industry": "AI 数据采集 / Web Data Infrastructure",
  "fields": [
    {
      "key": "data_collection_capabilities",
      "label": "数据采集能力",
      "type": "text",
      "required": false,
      "source_requirements": ["official_website", "docs", "blog"],
      "query_templates": ["{competitor} {label} official"]
    }
  ]
}
```

字段 key 规则：

- 常见维度使用内置映射，例如 `价格策略 -> pricing_strategy`、`安全合规 -> security_compliance`、`数据采集能力 -> data_collection_capabilities`。
- 未知维度不会丢弃；如果包含英文/数字，会生成稳定英文 key，例如 `MCP 支持 -> mcp_support`。
- 纯中文未知维度会生成 `dimension_{index}_{hash}`，保证不同任务之间稳定可存储。

`CompetitorProfileService` 会按竞品读取 Claim，并根据 `claim_type` 和关键词匹配到动态字段：

- `pricing` 优先进入 `pricing_strategy`。
- `security` 优先进入 `security_compliance / enterprise_capabilities`。
- `market` 优先进入 `target_users / positioning`。
- `feature` 优先进入 `core_features / agent_capabilities / ide_integration`。
- 如果字段 label 出现在 Claim 文本中，也会视为相关。

`profile_data_json` 示例：

```json
{
  "pricing_strategy": {
    "value": "Apify 提供按量和套餐计费，适合爬虫与数据采集任务。",
    "claim_ids": [101],
    "evidence_ids": [201, 202],
    "confidence": 0.86
  },
  "mcp_support": {
    "value": null,
    "claim_ids": [],
    "evidence_ids": [],
    "confidence": 0,
    "missing_reason": "缺少相关 Claim"
  }
}
```

`ComparisonMatrixService` 会基于所有竞品画像生成整体矩阵：

```json
{
  "columns": ["Apify", "Bright Data", "Tavily"],
  "rows": [
    { "key": "pricing_strategy", "label": "价格策略" },
    { "key": "developer_ecosystem", "label": "开发者生态" }
  ]
}
```

前端报告页会动态渲染：

- `ComparisonMatrixTable.vue`：按 `matrix_schema_json.columns` 和 `matrix_data_json.rows` 展示“维度 + 每个竞品一列”。
- `CompetitorProfileCards.vue` 保留为可复用组件，但报告页默认不展示画像卡片；因为矩阵本身就是由 `CompetitorProfile` 转置生成，二者信息源相同，矩阵更适合竞品横向对比。

### 8. 报告生成与段落溯源

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

ReportWriter 现在会同时接收：

- `claims`
- `evidence`
- `competitor_profiles`
- `comparison_matrices`

报告要求优先基于动态画像和动态矩阵组织内容，但关键段落仍必须引用已有 `claim_ids`。`report_json` 会额外保存：

```json
{
  "profile_ids": [1, 2, 3],
  "matrix_ids": [1]
}
```

### 9. QA 反馈闭环

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
- 展示动态维度 Analyst 分支。
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
| `claim_type` | 当前动态维度 Claim 使用 `dimension`；历史任务可能仍是 `feature / pricing / market / security` |
| `dimension_key` | 动态分析维度 key |
| `dimension_label` | 动态分析维度名称 |
| `dimension_prompt_json` | 生成该 Claim 使用的维度 prompt spec |
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
| `report_json` | 结构化报告，包含 sections / paragraphs / claim_ids / evidence_ids / profile_ids / matrix_ids |

### `competitor_profile`

动态竞品画像表。本表不包含任何行业固定画像列，所有维度字段都来自用户最终确认后的 `analysis_dimensions`。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `competitor_name` | 竞品名 |
| `template_key` | 场景模板 key，可为空 |
| `profile_schema_json` | 动态画像 Schema，包含 fields |
| `profile_data_json` | 每个动态字段的值、claim_ids、evidence_ids、confidence |
| `claim_ids_json` | 画像使用到的 Claim ID |
| `evidence_ids_json` | 画像使用到的 Evidence ID |
| `created_at / updated_at` | 北京时间 |

唯一约束：

```text
task_id + competitor_name
```

### `comparison_matrix`

动态对比矩阵表。矩阵列和行都来自动态画像，不写死字段。

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务 ID |
| `template_key` | 场景模板 key，可为空 |
| `matrix_type` | 矩阵类型，目前为 `overall` |
| `title` | 矩阵标题 |
| `matrix_schema_json` | 矩阵 Schema，包含 columns / rows |
| `matrix_data_json` | 矩阵数据，包含每个竞品在每个维度上的 summary / claim_ids / evidence_ids / confidence |
| `claim_ids_json` | 矩阵使用到的 Claim ID |
| `evidence_ids_json` | 矩阵使用到的 Evidence ID |
| `created_at / updated_at` | 北京时间 |

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
| `GET` | `/api/v1/analysis-tasks/{task_id}/profiles` | 动态竞品画像 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/matrices` | 动态对比矩阵 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/metrics` | 运行指标，包含证据覆盖率、来源多样性、QA、RAG fallback 等 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report` | 报告、Claim、Evidence、QA payload、动态画像和矩阵；前端报告页默认只展示矩阵 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report/export?format=markdown` | 导出完整 Markdown 报告文件，包含报告正文、动态对比矩阵、QA 结果和结构化结论；动态对比矩阵使用标准 Markdown 表格 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/report/export?format=pdf` | 导出完整 PDF 报告文件，包含报告正文、动态对比矩阵、QA 结果和结构化结论；PDF 会识别 Markdown 表格并渲染为真实表格，宽表会按列分块以避免页面溢出 |
| `GET` | `/api/v1/analysis-tasks/{task_id}/qa` | QA 结果 |

任务控制说明：

- 暂停和取消是协作式控制，不会强杀正在进行中的 Firecrawl、LLM、Embedding 或 Milvus 调用。
- 后端会在每个 Agent 节点开始前，以及采集、证据抽取、分析循环中检查控制状态。
- 暂停后的任务状态为 `paused`，恢复时重新入队，已经 `success` 的节点会跳过，`paused` 节点会继续执行。
- 取消后的任务状态为 `canceled`，不会自动清理已经写入的中间数据。
- 重试会清理该任务旧的 `source_document / evidence_chunk / claim / claim_evidence / competitor_profile / comparison_matrix / report / qa_result`，并将所有节点重置为 `pending` 后重新执行。
- Celery 任务的自动业务 retry 已关闭，失败后不会自己反复重跑；需要用户在前端手动点击“重试”。

Metrics API 说明：

```http
GET /api/v1/analysis-tasks/{task_id}/metrics
```

该接口只查询 MySQL，不调用 Firecrawl、DeepSeek、DashScope 或 Milvus。当前返回：

- `source_document_count`
- `evidence_chunk_count`
- `embedded_chunk_count`
- `embedding_failed_count`
- `claim_count`
- `claim_with_evidence_count`
- `evidence_coverage`
- `used_evidence_count`
- `evidence_usage_rate`
- `profile_count`
- `matrix_count`
- `qa_score`
- `qa_passed`
- `revision_count`
- `source_diversity`
- `competitor_coverage`
- `rag_query_count`
- `rag_fallback_count`
- `external_error_count`
- `node_durations`

前端 `TaskMetricsPanel.vue` 已接入任务详情页。任务详情页轮询任务状态时会同步刷新 Metrics，因此运行中可以看到来源数、Claim 数、画像/矩阵数量、证据覆盖率、Evidence 使用率、QA 分数和节点耗时变化。

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
LLM_THINKING_ENABLED=false
LLM_REASONING_EFFORT=high

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
   - 动态维度 Analyst 分支。
   - QA 回流边。
   - Agent 日志。
7. 进入阶段耗时页查看证据抽取每轮耗时。
8. 进入证据链页查看网页来源。
9. 进入报告页展开段落依据，查看 Claim 和 Evidence。
10. 进入历史记录页查看历史任务。

## 已验证

代码层面已做过：

```powershell
python -m compileall app
npm run build
```

前端构建会出现 Element Plus / Rolldown 的 pure annotation warning 和 chunk size warning，目前不影响运行。

## 当前能力边界

系统已经是可运行 MVP+，但仍有一些边界：

- 分析阶段采用动态维度 Analyst：每个分析维度一个独立 Agent，并在后端真正并行执行。
- 动态维度 Analyst 采用严格失败策略：除“该维度没有检索到 evidence”外，LLM/JSON/DB/Milvus 等真实失败都会中断任务，防止空报告。
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
2. 为并行 Analyst 增加独立超时、限流和更清晰的失败恢复入口。
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
