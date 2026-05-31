from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_bj


class CompetitorProfile(Base):
    __tablename__ = "competitor_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    competitor_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    template_key: Mapped[str | None] = mapped_column(String(100), index=True)
    profile_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    profile_data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    claim_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    evidence_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, onupdate=now_bj, nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "competitor_name", name="uq_profile_task_competitor"),
        Index("ix_profile_task_template", "task_id", "template_key"),
    )
