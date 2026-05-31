from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.matrix import ComparisonMatrixItem
from app.schemas.profile import CompetitorProfileItem


class ReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    content_markdown: str
    content_html: str | None
    report_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ReportClaimItem(BaseModel):
    id: int
    task_id: int
    claim_text: str
    competitor_name: str | None = None
    claim_type: str | None = None
    dimension_key: str | None = None
    dimension_label: str | None = None
    confidence: Decimal | None = None
    risk_level: str | None = None
    evidence_ids: list[int] = []
    created_at: datetime


class ReportEvidenceItem(BaseModel):
    id: int
    source_url: str
    source_title: str | None = None
    source_type: str | None = None
    chunk_text: str
    competitor_name: str | None = None
    reliability_score: Decimal | None = None


class ReportResponse(BaseModel):
    report: ReportItem | None
    claims: list[ReportClaimItem] = []
    evidence: list[ReportEvidenceItem] = []
    qa_result: dict | None = None
    profiles: list[CompetitorProfileItem] = []
    matrices: list[ComparisonMatrixItem] = []
