from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_node import AgentNode
from app.models.agent_run_log import AgentRunLog


def add_log(db: Session, task_id: int, node_id: int | None, message: str, payload: dict | None = None, log_type: str = "info") -> AgentRunLog:
    log = AgentRunLog(task_id=task_id, node_id=node_id, log_type=log_type, message=message, payload_json=payload)
    db.add(log)
    db.flush()
    return log


def list_logs(db: Session, task_id: int, node_key: str | None = None) -> list[AgentRunLog]:
    stmt = select(AgentRunLog).where(AgentRunLog.task_id == task_id).order_by(AgentRunLog.id)
    if node_key:
        stmt = stmt.join(AgentNode, AgentNode.id == AgentRunLog.node_id).where(AgentNode.node_key == node_key)
    return list(db.scalars(stmt))
