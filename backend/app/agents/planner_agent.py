import json
import re

from app.schemas.task_plan import TaskPlan
from app.tools.llm_client import LLMClient


DEMO_INPUT = "请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。"


def _default_task_plan() -> TaskPlan:
    return TaskPlan(
        topic="AI 编程助手市场竞品分析",
        industry="AI 编程助手 / AI IDE",
        target_product=None,
        competitors=["Cursor", "GitHub Copilot", "Windsurf", "Tabnine"],
        analysis_dimensions=["产品定位", "核心功能", "Agent 能力", "IDE 集成", "价格策略", "企业能力", "安全合规", "适用用户"],
        report_depth="standard",
        output_language="zh-CN",
        auto_discover_competitors=False,
        data_sources=["official_website", "pricing_page", "docs", "blog", "news", "reviews"],
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
  "auto_discover_competitors": false,
  "data_sources": ["official_website","pricing_page","docs","blog","news","reviews"]
}}
"""
    try:
        content = LLMClient().complete(prompt, system="你只输出合法 JSON。")
        data = _json_from_text(content)
        plan = TaskPlan(**data)
        if not plan.competitors or not plan.analysis_dimensions:
            return _default_task_plan()
        return plan
    except Exception:
        return _default_task_plan()
