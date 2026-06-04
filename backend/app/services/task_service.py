import hashlib

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.core.timezone import now_bj
from app.models.agent_node import AgentNode
from app.models.agent_run_log import AgentRunLog
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
    ("report_finalizer", "报告总结 Agent", "report_finalizer"),
]

DAG_EDGES = [
    {"source": "planner", "target": "dimension_planner", "type": "normal"},
    {"source": "dimension_planner", "target": "collector", "type": "normal"},
    {"source": "collector", "target": "evidence_extractor", "type": "normal"},
    {"source": "report_writer", "target": "qa", "type": "normal"},
    {"source": "qa", "target": "report_finalizer", "type": "normal"},
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


def _revision_route(next_action: str | None, target_nodes: list[str]) -> list[str]:
    targets = [str(node_key) for node_key in target_nodes if str(node_key).startswith("dimension_analysis_")]
    if next_action == "recollect":
        return ["collector", "evidence_extractor", *targets, "report_writer", "qa"]
    if next_action == "reanalyze":
        return [*targets, "report_writer", "qa"]
    if next_action == "rewrite":
        return ["report_writer", "qa"]
    return []


def _latest_revision_marker(db: Session, task_id: int) -> tuple[dict | None, object | None]:
    log = db.scalar(
        select(AgentRunLog)
        .where(AgentRunLog.task_id == task_id, AgentRunLog.message == "QA requested revision")
        .order_by(AgentRunLog.id.desc())
    )
    if log is None or not isinstance(log.payload_json, dict):
        return None, None
    return log.payload_json, log.created_at


def _revision_marker_is_active(
    task: AnalysisTask | None,
    latest_qa: QAResult | None,
    revision_payload: dict | None,
    revision_started_at: object | None,
) -> bool:
    def revision_round(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    if task is None or latest_qa is None or latest_qa.passed or revision_started_at is None:
        return False
    if task.status not in {
        "running",
        "collecting",
        "extracting",
        "analyzing",
        "writing",
        "qa_checking",
        "pause_requested",
        "paused",
    }:
        return False
    latest_qa_payload = latest_qa.issues_json if isinstance(latest_qa.issues_json, dict) else {}
    marker_round = revision_round((revision_payload or {}).get("revision_round"))
    latest_qa_round = revision_round(latest_qa_payload.get("revision_round"))
    if marker_round > 0:
        return latest_qa_round < marker_round
    latest_qa_created_at = getattr(latest_qa, "created_at", None)
    if latest_qa_created_at is None:
        return True
    return latest_qa_created_at <= revision_started_at


def list_nodes(db: Session, task_id: int) -> list[dict]:
    nodes = list(db.scalars(select(AgentNode).where(AgentNode.task_id == task_id).order_by(AgentNode.id)))
    task = db.get(AnalysisTask, task_id)
    payload, revision_started_at = _latest_revision_marker(db, task_id)
    latest_qa = db.scalar(select(QAResult).where(QAResult.task_id == task_id).order_by(QAResult.id.desc()))
    route: list[str] = []
    revision_label = None
    if payload and _revision_marker_is_active(task, latest_qa, payload, revision_started_at):
        route = _revision_route(payload.get("next_action"), payload.get("target_nodes") or [])
        revision_label = f"Revision {payload.get('revision_round') or ''}".strip()
    result = []
    for node in nodes:
        node_payload = {
            "id": node.id,
            "task_id": node.task_id,
            "node_key": node.node_key,
            "node_name": node.node_name,
            "node_type": node.node_type,
            "status": node.status,
            "input_summary": node.input_summary,
            "output_summary": node.output_summary,
            "started_at": node.started_at,
            "ended_at": node.ended_at,
            "duration_ms": node.duration_ms,
            "retry_count": node.retry_count,
            "error_message": node.error_message,
            "revision_highlight": False,
            "revision_label": None,
        }
        if node.node_key in route and revision_started_at is not None:
            completed_this_revision = (
                node.status == "success"
                and node.started_at is not None
                and node.started_at >= revision_started_at
            )
            node_payload["revision_highlight"] = not completed_this_revision
            node_payload["revision_label"] = revision_label if not completed_this_revision else None
        result.append(node_payload)
    return result


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
    return edges
