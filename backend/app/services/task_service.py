import hashlib

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.core.timezone import now_bj
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.comparison_matrix import ComparisonMatrix
from app.models.competitor_profile import CompetitorProfile
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.schemas.analysis_task import AnalysisTaskCreateRequest
from app.schemas.task_plan import TaskPlan
from app.services.profile_schema_builder import ProfileSchemaBuilder


NODE_DEFINITIONS = [
    ("planner", "任务规划 Agent", "planner"),
    ("dimension_planner", "维度 Prompt Planner Agent", "dimension_planner"),
    ("collector", "资料采集 Agent", "collector"),
    ("evidence_extractor", "证据抽取 Agent", "evidence_extractor"),
    ("report_writer", "报告撰写 Agent", "writer"),
    ("qa", "质量检查 Agent", "qa"),
]

DAG_EDGES = [
    {"source": "planner", "target": "dimension_planner", "type": "normal"},
    {"source": "dimension_planner", "target": "collector", "type": "normal"},
    {"source": "collector", "target": "evidence_extractor", "type": "normal"},
    {"source": "report_writer", "target": "qa", "type": "normal"},
]


def dimension_node_key(dimension_key: str) -> str:
    safe_key = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in dimension_key.lower()).strip("_")
    digest = hashlib.sha1(dimension_key.encode("utf-8")).hexdigest()[:8]
    return f"dimension_analysis_{safe_key[:60]}_{digest}"


def build_dimension_node_specs(plan: TaskPlan) -> list[dict]:
    schema = ProfileSchemaBuilder().build_schema(plan.model_dump())
    specs = []
    for field in schema.get("fields", []):
        dimension_key = str(field.get("key") or "").strip()
        dimension_label = str(field.get("label") or dimension_key).strip()
        if not dimension_key or not dimension_label:
            continue
        specs.append(
            {
                "node_key": dimension_node_key(dimension_key),
                "node_name": f"{dimension_label}分析 Agent",
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "field": field,
            }
        )
    return specs


def ensure_dimension_nodes(db: Session, task: AnalysisTask, plan: TaskPlan | None = None) -> list[AgentNode]:
    plan = plan or get_task_plan(task)
    specs = build_dimension_node_specs(plan)
    existing = {node.node_key: node for node in db.scalars(select(AgentNode).where(AgentNode.task_id == task.id))}
    nodes = []
    for spec in specs:
        node = existing.get(spec["node_key"])
        if node is None:
            node = AgentNode(
                task_id=task.id,
                node_key=spec["node_key"],
                node_name=spec["node_name"],
                node_type="dimension_analyst",
                status="pending",
            )
            db.add(node)
            db.flush()
        else:
            node.node_name = spec["node_name"]
            node.node_type = "dimension_analyst"
        nodes.append(node)
    return nodes


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
    ensure_dimension_nodes(db, task, plan)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> AnalysisTask | None:
    return db.get(AnalysisTask, task_id)


def list_tasks(db: Session, limit: int = 50, offset: int = 0) -> list[AnalysisTask]:
    return list(
        db.scalars(
            select(AnalysisTask)
            .options(selectinload(AnalysisTask.nodes))
            .order_by(AnalysisTask.created_at.desc(), AnalysisTask.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )


def update_task_status(db: Session, task_id: int, status: str, error_message: str | None = None) -> None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return
    task.status = status
    task.error_message = error_message
    task.updated_at = now_bj()
    db.commit()


def request_cancel_task(db: Session, task_id: int) -> AnalysisTask | None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return None
    if task.status in {"success", "failed", "canceled"}:
        task.status = "canceled"
    elif task.status == "queued":
        task.status = "canceled"
    else:
        task.status = "cancel_requested"
    task.error_message = "任务取消请求已提交"
    task.updated_at = now_bj()
    for node in task.nodes:
        if node.status in {"pending", "running", "paused"}:
            node.status = "canceled" if task.status == "canceled" else node.status
    db.commit()
    db.refresh(task)
    return task


def request_pause_task(db: Session, task_id: int) -> AnalysisTask | None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return None
    if task.status in {"success", "failed", "canceled"}:
        return task
    task.status = "paused" if task.status == "queued" else "pause_requested"
    task.error_message = "任务暂停请求已提交"
    task.updated_at = now_bj()
    db.commit()
    db.refresh(task)
    return task


def mark_task_resuming(db: Session, task_id: int) -> AnalysisTask | None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return None
    if task.status not in {"paused", "pause_requested"}:
        return task
    task.status = "queued"
    task.error_message = None
    task.updated_at = now_bj()
    for node in task.nodes:
        if node.status == "paused":
            node.status = "pending"
            node.error_message = None
    db.commit()
    db.refresh(task)
    return task


def reset_task_for_retry(db: Session, task_id: int) -> AnalysisTask | None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return None

    claim_ids = select(Claim.id).where(Claim.task_id == task_id)
    evidence_ids = select(EvidenceChunk.id).where(EvidenceChunk.task_id == task_id)
    db.execute(delete(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids)).execution_options(synchronize_session=False))
    db.execute(delete(ClaimEvidence).where(ClaimEvidence.evidence_chunk_id.in_(evidence_ids)).execution_options(synchronize_session=False))
    db.execute(delete(QAResult).where(QAResult.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(Report).where(Report.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(CompetitorProfile).where(CompetitorProfile.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(Claim).where(Claim.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(EvidenceChunk).where(EvidenceChunk.task_id == task_id).execution_options(synchronize_session=False))
    db.execute(delete(SourceDocument).where(SourceDocument.task_id == task_id).execution_options(synchronize_session=False))

    existing_node_keys = {node.node_key for node in task.nodes}
    for node_key, node_name, node_type in NODE_DEFINITIONS:
        if node_key not in existing_node_keys:
            db.add(AgentNode(task_id=task.id, node_key=node_key, node_name=node_name, node_type=node_type, status="pending"))
    ensure_dimension_nodes(db, task)
    db.flush()

    nodes = list(db.scalars(select(AgentNode).where(AgentNode.task_id == task_id)))
    for node in nodes:
        node.status = "pending"
        node.input_summary = None
        node.output_summary = None
        node.started_at = None
        node.ended_at = None
        node.duration_ms = None
        node.retry_count += 1
        node.error_message = None
    task.status = "queued"
    task.error_message = None
    task.updated_at = now_bj()
    db.commit()
    db.refresh(task)
    return task


def get_task_plan(task: AnalysisTask) -> TaskPlan:
    if task.task_plan_json:
        return TaskPlan(**task.task_plan_json)
    return parse_task_plan(task.user_input)


def list_nodes(db: Session, task_id: int) -> list[AgentNode]:
    return list(db.scalars(select(AgentNode).where(AgentNode.task_id == task_id).order_by(AgentNode.id)))


def list_edges(db: Session, task_id: int) -> list[dict]:
    edges = [dict(edge) for edge in DAG_EDGES]
    dimension_nodes = list(
        db.scalars(
            select(AgentNode)
            .where(AgentNode.task_id == task_id, AgentNode.node_type == "dimension_analyst")
            .order_by(AgentNode.id)
        )
    )
    for node in dimension_nodes:
        edges.append({"source": "evidence_extractor", "target": node.node_key, "type": "normal"})
        edges.append({"source": node.node_key, "target": "report_writer", "type": "normal"})
    existing_keys = {
        row
        for row in db.scalars(
            select(AgentNode.node_key).where(
                AgentNode.task_id == task_id,
                AgentNode.node_key.in_(["feature_analysis", "pricing_analysis", "market_analysis", "security_analysis"]),
            )
        )
    }
    for node_key in sorted(existing_keys):
        edges.append({"source": "evidence_extractor", "target": node_key, "type": "normal"})
        edges.append({"source": node_key, "target": "report_writer", "type": "normal"})
    qa_results = list(db.scalars(select(QAResult).where(QAResult.task_id == task_id).order_by(QAResult.id.desc())))
    for qa_result in qa_results:
        payload = qa_result.issues_json
        if not isinstance(payload, dict):
            continue
        next_action = payload.get("next_action")
        target_nodes = payload.get("target_nodes") or []
        if next_action in {"recollect", "reanalyze", "rewrite"}:
            targets = target_nodes or (["collector"] if next_action == "recollect" else ["report_writer"])
            for target in targets:
                edges.append({"source": "qa", "target": target, "type": "revision", "label": "QA Revision"})
            break
    return edges
