from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timezone import now_bj


class AgentNode(Base):
    __tablename__ = "agent_node"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_task.id"), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    qa_passed: Mapped[bool | None] = mapped_column(Boolean)
    qa_score: Mapped[float | None] = mapped_column(Numeric(4, 2))
    qa_revision_round: Mapped[int | None] = mapped_column(Integer)
    qa_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    qa_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, onupdate=now_bj, nullable=False)

    task = relationship("AnalysisTask", back_populates="nodes")
