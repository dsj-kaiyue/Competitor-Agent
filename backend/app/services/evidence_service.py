from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_chunk import EvidenceChunk


def list_evidence(db: Session, task_id: int, competitor_name: str | None = None, source_type: str | None = None) -> list[EvidenceChunk]:
    stmt = select(EvidenceChunk).where(EvidenceChunk.task_id == task_id)
    if competitor_name:
        stmt = stmt.where(EvidenceChunk.competitor_name == competitor_name)
    if source_type:
        stmt = stmt.where(EvidenceChunk.source_type == source_type)
    return list(db.scalars(stmt.order_by(EvidenceChunk.id)))
