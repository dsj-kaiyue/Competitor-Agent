from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComparisonMatrixItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    template_key: str | None = None
    matrix_type: str
    title: str
    matrix_schema_json: dict
    matrix_data_json: dict
    claim_ids_json: list[int] | None = None
    evidence_ids_json: list[int] | None = None
    created_at: datetime
    updated_at: datetime


class ComparisonMatrixListResponse(BaseModel):
    items: list[ComparisonMatrixItem] = []
