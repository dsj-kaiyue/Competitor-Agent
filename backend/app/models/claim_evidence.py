from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_bj


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"), nullable=False, index=True)
    evidence_chunk_id: Mapped[int] = mapped_column(ForeignKey("evidence_chunk.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
