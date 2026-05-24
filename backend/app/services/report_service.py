from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report


def get_report(db: Session, task_id: int) -> Report | None:
    return db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))
