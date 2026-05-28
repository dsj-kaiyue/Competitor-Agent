from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timezone import now_bj


class AnalysisTask(Base):
    __tablename__ = "analysis_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    target_product: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created")
    report_depth: Mapped[str] = mapped_column(String(50), default="standard")
    output_language: Mapped[str] = mapped_column(String(50), default="zh-CN")
    task_plan_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, onupdate=now_bj, nullable=False)

    nodes = relationship("AgentNode", back_populates="task", cascade="all, delete-orphan")
