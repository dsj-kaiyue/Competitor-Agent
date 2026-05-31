from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompetitorProfileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    competitor_name: str
    template_key: str | None = None
    profile_schema_json: dict
    profile_data_json: dict
    claim_ids_json: list[int] | None = None
    evidence_ids_json: list[int] | None = None
    created_at: datetime
    updated_at: datetime


class CompetitorProfileListResponse(BaseModel):
    items: list[CompetitorProfileItem] = []
