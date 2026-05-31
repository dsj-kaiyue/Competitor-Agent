from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_bj


class ComparisonMatrix(Base):
    __tablename__ = "comparison_matrix"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    template_key: Mapped[str | None] = mapped_column(String(100), index=True)
    matrix_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    matrix_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    matrix_data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    claim_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    evidence_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, onupdate=now_bj, nullable=False)

    __table_args__ = (Index("ix_matrix_task_type", "task_id", "matrix_type"),)
