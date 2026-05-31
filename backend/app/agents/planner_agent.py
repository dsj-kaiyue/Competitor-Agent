import json
import re

from app.schemas.task_plan import TaskPlan
from app.tools.llm_client import LLMClient
from app.tools.web_context_provider import WebContextProvider


DEFAULT_DIMENSIONS = ["产品定位", "核心功能", "目标用户", "价格策略", "优势劣势", "市场表现", "安全合规"]
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
        template_key=None,
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


def _normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ，。,.").casefold()


def discover_competitors_for_plan(plan: TaskPlan, max_competitors: int = 6) -> list[str]:
    target = plan.target_product or plan.topic
    discovery_query = f"{target} competitors alternatives {plan.industry or ''}".strip()
    discovery_results = WebContextProvider().search(discovery_query, max_results=8)
    discovery_context = "\n".join(
        f"- title={item.get('title')}; url={item.get('url')}; description={item.get('description') or item.get('markdown') or ''}"
        for item in discovery_results
    )
    prompt = f"""
请从搜索结果中识别与目标产品最相关的直接竞品或替代产品。
目标产品：{target}
行业：{plan.industry}
搜索结果：
{discovery_context}

只输出 JSON 数组，最多 {max_competitors} 个产品名。不要包含目标产品本身，不要输出解释。
"""
    discovered = _json_from_text(LLMClient().complete(prompt, system="你只输出合法 JSON。"))
    if isinstance(discovered, dict):
        discovered = discovered.get("competitors", [])
    existing_names = {_normalized_name(name) for name in plan.competitors}
    target_name = _normalized_name(target or "")
    merged: list[str] = []
    for name in discovered:
        candidate = str(name).strip()
        normalized = _normalized_name(candidate)
        if not candidate or normalized == target_name or normalized in existing_names:
            continue
        existing_names.add(normalized)
        merged.append(candidate)
        if len(merged) >= max_competitors:
            break
    return merged


def suggest_analysis_dimensions_for_plan(user_input: str, plan: TaskPlan, max_dimensions: int = 5) -> list[str]:
    existing = [dimension for dimension in plan.analysis_dimensions if dimension.strip()]
    prompt = f"""
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
"""
    suggested = _json_from_text(LLMClient().complete(prompt, system="你只输出合法 JSON。"))
    if isinstance(suggested, dict):
        suggested = suggested.get("analysis_dimensions", [])
    existing_names = {_normalized_name(dimension) for dimension in existing}
    merged: list[str] = []
    for dimension in suggested:
        candidate = str(dimension).strip()
        normalized = _normalized_name(candidate)
        if not candidate or normalized in existing_names:
            continue
        existing_names.add(normalized)
        merged.append(candidate)
        if len(merged) >= max_dimensions:
            break
    return merged


def _supplement_plan(
    user_input: str,
    plan: TaskPlan,
    *,
    auto_discover_competitors: bool,
    auto_add_analysis_dimensions: bool,
) -> TaskPlan:
    plan.auto_discover_competitors = auto_discover_competitors
    if not plan.analysis_dimensions:
        plan.analysis_dimensions = DEFAULT_DIMENSIONS
    if not plan.data_sources:
        plan.data_sources = DEFAULT_DATA_SOURCES
    if auto_add_analysis_dimensions:
        try:
            plan.analysis_dimensions = [
                *plan.analysis_dimensions,
                *suggest_analysis_dimensions_for_plan(user_input, plan),
            ]
        except Exception:
            pass
    if auto_discover_competitors:
        try:
            plan.competitors = [*plan.competitors, *discover_competitors_for_plan(plan)]
        except Exception:
            pass
    return plan


def parse_task_plan(
    user_input: str,
    auto_discover_competitors: bool = False,
    auto_add_analysis_dimensions: bool = True,
) -> TaskPlan:
    prompt = f"""
你是竞品分析 Planner Agent。请把用户输入解析成通用竞品分析 TaskPlan。
你需要根据用户输入判断本次竞品分析场景，并推荐适合该场景的分析维度。

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
  "data_sources": ["official_website","pricing_page","docs","blog","news","reviews"],
  "template_key": "string or null"
}}

规则：
- 如果用户只给了目标产品和行业，没有明确列出竞品，competitors 输出空数组，并把 auto_discover_competitors 设为 true。
- 不要使用示例产品或默认竞品填充结果。
- topic、industry、target_product 必须忠实来自用户输入。
- analysis_dimensions 必须根据行业和用户场景动态生成，不能固定返回 AI 编程助手维度。
- 如果用户明确写了“重点关注 xxx”，必须优先保留这些维度。
- 如果用户没有指定维度，根据行业自动推荐 5 到 8 个中文短语维度，适合直接展示给用户编辑。
- AI 数据采集场景可包含“数据采集能力”“网页抓取能力”“结构化抽取能力”“开发者生态”等；AI 搜索场景可包含“搜索能力”“引用质量”“研究报告能力”等；新能源汽车场景可包含“车型定位”“续航能力”“智能驾驶”等。
"""
    try:
        content = LLMClient().complete(prompt, system="你只输出合法 JSON。")
        data = _json_from_text(content)
        plan = TaskPlan(**data)
        return _supplement_plan(
            user_input,
            plan,
            auto_discover_competitors=auto_discover_competitors,
            auto_add_analysis_dimensions=auto_add_analysis_dimensions,
        )
    except Exception:
        plan = _infer_task_plan(user_input)
        return _supplement_plan(
            user_input,
            plan,
            auto_discover_competitors=auto_discover_competitors,
            auto_add_analysis_dimensions=auto_add_analysis_dimensions,
        )
