from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QAIssue(BaseModel):
    type: Literal[
        "missing_evidence",
        "weak_evidence",
        "unsupported_claim",
        "contradiction",
        "outdated_source",
        "schema_incomplete",
        "logic_gap",
        "writing_issue",
    ]
    severity: Literal["low", "medium", "high"]
    message: str
    related_claim_id: int | None = None
    related_competitor: str | None = None
    related_dimension: str | None = None
    suggested_action: Literal["recollect", "reanalyze", "rewrite", "ignore"]
    target_node: str | None = None
    search_query: str | None = None


class QAResultPayload(BaseModel):
    passed: bool
    score: float = Field(ge=0, le=1)
    issues: list[QAIssue] = []
    next_action: Literal["end", "recollect", "reanalyze", "rewrite"] = "end"
    target_nodes: list[str] = []
    revision_reason: str | None = None
    followup_queries: list[str] = []
    revision_round: int = 0


class QAResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    report_id: int | None
    passed: bool
    score: Decimal | None
    issues: list[dict]
    next_action: str = "end"
    next_action_label: str = "无需返工"
    target_nodes: list[str] = []
    target_node_labels: list[str] = []
    revision_reason: str | None = None
    revision_round: int = 0
    created_at: datetime


class QAResultResponse(BaseModel):
    qa_result: QAResultItem | None
