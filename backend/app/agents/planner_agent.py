from app.schemas.task_plan import TaskPlan


DEMO_INPUT = "请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。"


def parse_task_plan(user_input: str) -> TaskPlan:
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
