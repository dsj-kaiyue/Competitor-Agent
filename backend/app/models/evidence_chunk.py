from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunk"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_task.id"), nullable=False, index=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), nullable=False)
    competitor_name: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str | None] = mapped_column(String(100))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    reliability_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    milvus_vector_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
