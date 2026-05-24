from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.qa_result import QAResult


def get_qa_result(db: Session, task_id: int) -> QAResult | None:
    return db.scalar(select(QAResult).where(QAResult.task_id == task_id).order_by(QAResult.id.desc()))
