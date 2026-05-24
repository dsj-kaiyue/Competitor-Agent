from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ClaimItem(BaseModel):
    id: int
    task_id: int
    competitor_name: str | None
    claim_type: str | None
    claim_text: str
    confidence: Decimal | None
    risk_level: str | None
    evidence_ids: list[int]
    created_at: datetime


class ClaimListResponse(BaseModel):
    items: list[ClaimItem]
