from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class QAResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    report_id: int | None
    passed: bool
    score: Decimal | None
    issues: list[dict]
    created_at: datetime


class QAResultResponse(BaseModel):
    qa_result: QAResultItem | None
