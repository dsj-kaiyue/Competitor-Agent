from datetime import datetime

from pydantic import BaseModel

from app.schemas.agent_node import AgentNodeResponse
from app.schemas.task_plan import TaskPlan


class AnalysisTaskCreateRequest(BaseModel):
    user_input: str
    task_plan: TaskPlan


class AnalysisTaskCreateResponse(BaseModel):
    task_id: int
    status: str


class AnalysisTaskResponse(BaseModel):
    id: int
    user_input: str
    topic: str
    industry: str | None
    target_product: str | None
    status: str
    report_depth: str
    output_language: str
    task_plan: TaskPlan
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisTaskHistoryItem(AnalysisTaskResponse):
    nodes: list[AgentNodeResponse]


class AnalysisTaskHistoryResponse(BaseModel):
    items: list[AnalysisTaskHistoryItem]
