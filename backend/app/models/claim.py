from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_bj


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_task.id"), nullable=False, index=True)
    agent_node_id: Mapped[int | None] = mapped_column(ForeignKey("agent_node.id"))
    competitor_name: Mapped[str | None] = mapped_column(String(255))
    claim_type: Mapped[str | None] = mapped_column(String(100))
    dimension_key: Mapped[str | None] = mapped_column(String(100), index=True)
    dimension_label: Mapped[str | None] = mapped_column(String(255))
    dimension_prompt_json: Mapped[dict | None] = mapped_column(JSON)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    risk_level: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_bj, nullable=False)
