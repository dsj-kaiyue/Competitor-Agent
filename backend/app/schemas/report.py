from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    content_markdown: str
    content_html: str | None
    created_at: datetime
    updated_at: datetime


class ReportResponse(BaseModel):
    report: ReportItem | None
