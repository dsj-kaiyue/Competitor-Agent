from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    node_key: str
    node_name: str
    node_type: str
    status: str
    input_summary: str | None = None
    output_summary: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    retry_count: int
    error_message: str | None = None


class DagEdge(BaseModel):
    source: str
    target: str


class AgentNodeListResponse(BaseModel):
    nodes: list[AgentNodeResponse]
    edges: list[DagEdge]


class AgentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    node_id: int | None
    log_type: str
    message: str
    payload: dict | None = None
    created_at: datetime


class AgentLogListResponse(BaseModel):
    logs: list[AgentLogResponse]
