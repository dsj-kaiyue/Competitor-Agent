from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.schemas.analysis_task import AnalysisTaskCreateRequest
from app.schemas.task_plan import TaskPlan


NODE_DEFINITIONS = [
    ("planner", "任务规划 Agent", "planner"),
    ("collector", "资料采集 Agent", "collector"),
    ("evidence_extractor", "证据抽取 Agent", "evidence_extractor"),
    ("feature_analysis", "功能分析 Agent", "analyst"),
    ("pricing_analysis", "价格分析 Agent", "analyst"),
    ("market_analysis", "市场分析 Agent", "analyst"),
    ("security_analysis", "安全合规分析 Agent", "analyst"),
    ("report_writer", "报告撰写 Agent", "writer"),
    ("qa", "质量检查 Agent", "qa"),
]

DAG_EDGES = [
    {"source": "planner", "target": "collector"},
    {"source": "collector", "target": "evidence_extractor"},
    {"source": "evidence_extractor", "target": "feature_analysis"},
    {"source": "feature_analysis", "target": "pricing_analysis"},
    {"source": "pricing_analysis", "target": "market_analysis"},
    {"source": "market_analysis", "target": "security_analysis"},
    {"source": "security_analysis", "target": "report_writer"},
    {"source": "report_writer", "target": "qa"},
]


def create_task(db: Session, request: AnalysisTaskCreateRequest) -> AnalysisTask:
    plan = request.task_plan
    task = AnalysisTask(
        user_input=request.user_input,
        topic=plan.topic,
        industry=plan.industry,
        target_product=plan.target_product,
        status="queued",
        report_depth=plan.report_depth,
        output_language=plan.output_language,
        task_plan_json=plan.model_dump(),
    )
    db.add(task)
    db.flush()
    for node_key, node_name, node_type in NODE_DEFINITIONS:
        db.add(AgentNode(task_id=task.id, node_key=node_key, node_name=node_name, node_type=node_type, status="pending"))
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> AnalysisTask | None:
    return db.get(AnalysisTask, task_id)


def update_task_status(db: Session, task_id: int, status: str, error_message: str | None = None) -> None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return
    task.status = status
    task.error_message = error_message
    task.updated_at = datetime.utcnow()
    db.commit()


def get_task_plan(task: AnalysisTask) -> TaskPlan:
    if task.task_plan_json:
        return TaskPlan(**task.task_plan_json)
    return parse_task_plan(task.user_input)


def list_nodes(db: Session, task_id: int) -> list[AgentNode]:
    return list(db.scalars(select(AgentNode).where(AgentNode.task_id == task_id).order_by(AgentNode.id)))
