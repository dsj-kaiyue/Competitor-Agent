import json
import re

from app.schemas.task_plan import TaskPlan
from app.tools.llm_client import LLMClient


DEFAULT_DIMENSIONS = ["产品定位", "核心功能", "目标用户", "数据能力", "技术架构", "价格策略", "生态集成", "安全合规"]
DEFAULT_DATA_SOURCES = ["official_website", "pricing_page", "docs", "blog", "news", "reviews"]


def _infer_task_plan(user_input: str) -> TaskPlan:
    cleaned = user_input.strip()
    target_product = None
    industry = None

    match = re.search(r"分析\s*(.+?)\s*在\s*(.+?)\s*的?竞品", cleaned)
    if match:
        target_product = match.group(1).strip(" ，。,.")
        industry = match.group(2).strip(" ，。,.")
    else:
        match = re.search(r"分析\s*(.+?)\s*的?竞品", cleaned)
        if match:
            target_product = match.group(1).strip(" ，。,.")

    if not target_product:
        target_product = cleaned[:80] or "待分析产品"

    return TaskPlan(
        topic=f"{target_product}竞品分析",
        industry=industry,
        target_product=target_product,
        competitors=[],
        analysis_dimensions=DEFAULT_DIMENSIONS,
        report_depth="standard",
        output_language="zh-CN",
        auto_discover_competitors=True,
        data_sources=DEFAULT_DATA_SOURCES,
    )


def _json_from_text(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_task_plan(user_input: str) -> TaskPlan:
    prompt = f"""
你是竞品分析 Planner Agent。请把用户输入解析成通用竞品分析 TaskPlan。

用户输入：
{user_input}

只输出 JSON，不要输出解释。格式：
{{
  "topic": "string",
  "industry": "string or null",
  "target_product": null,
  "competitors": ["string"],
  "analysis_dimensions": ["string"],
  "report_depth": "simple|standard|deep",
  "output_language": "zh-CN",
  "auto_discover_competitors": true,
  "data_sources": ["official_website","pricing_page","docs","blog","news","reviews"]
}}

规则：
- 如果用户只给了目标产品和行业，没有明确列出竞品，competitors 输出空数组，并把 auto_discover_competitors 设为 true。
- 不要使用示例产品或默认竞品填充结果。
- topic、industry、target_product 必须忠实来自用户输入。
"""
    try:
        content = LLMClient().complete(prompt, system="你只输出合法 JSON。")
        data = _json_from_text(content)
        plan = TaskPlan(**data)
        if not plan.analysis_dimensions:
            plan.analysis_dimensions = DEFAULT_DIMENSIONS
        if not plan.data_sources:
            plan.data_sources = DEFAULT_DATA_SOURCES
        if not plan.competitors:
            plan.auto_discover_competitors = True
        return plan
    except Exception:
        return _infer_task_plan(user_input)
