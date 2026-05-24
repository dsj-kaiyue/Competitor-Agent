from pydantic import BaseModel, Field


class TaskPlan(BaseModel):
    topic: str
    industry: str | None = None
    target_product: str | None = None
    competitors: list[str] = Field(default_factory=list)
    analysis_dimensions: list[str] = Field(default_factory=list)
    report_depth: str = "standard"
    output_language: str = "zh-CN"
    auto_discover_competitors: bool = False
    data_sources: list[str] = Field(default_factory=list)


class TaskPlanParseRequest(BaseModel):
    user_input: str


class TaskPlanParseResponse(BaseModel):
    task_plan: TaskPlan
