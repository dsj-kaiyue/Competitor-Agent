from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class EvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    competitor_name: str | None
    source_url: str
    source_title: str | None
    source_type: str | None
    chunk_index: int
    chunk_text: str
    reliability_score: Decimal | None
    created_at: datetime


class EvidenceListResponse(BaseModel):
    items: list[EvidenceItem]
