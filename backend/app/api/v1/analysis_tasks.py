from threading import Thread
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.celery_app import CELERY_QUEUE_NAME
from app.core.database import SessionLocal, get_db
from app.core.redis_runtime import get_worker_heartbeat
from app.graph.workflow import _console
from app.schemas.agent_node import AgentLogListResponse, AgentLogResponse, AgentNodeListResponse
from app.schemas.analysis_task import (
    AnalysisTaskCreateRequest,
    AnalysisTaskCreateResponse,
    AnalysisTaskHistoryItem,
    AnalysisTaskHistoryResponse,
    AnalysisTaskResponse,
)
from app.schemas.claim import ClaimItem, ClaimListResponse
from app.schemas.evidence import EvidenceListResponse
from app.schemas.matrix import ComparisonMatrixItem, ComparisonMatrixListResponse
from app.schemas.metrics import TaskMetricsResponse
from app.schemas.profile import CompetitorProfileItem, CompetitorProfileListResponse
from app.schemas.qa import QAResultItem, QAResultResponse
from app.schemas.report import ReportClaimItem, ReportEvidenceItem, ReportItem, ReportResponse
from app.models.comparison_matrix import ComparisonMatrix
from app.models.competitor_profile import CompetitorProfile
from app.services.claim_service import list_claims_with_evidence
from app.services.evidence_service import list_evidence
from app.services.log_service import list_logs
from app.services.metrics_service import MetricsService
from app.services.qa_service import get_qa_result
from app.services.report_service import build_markdown_export, build_pdf_export, get_report, safe_report_filename
from app.services.task_service import (
    create_task,
    get_task,
    get_task_plan,
    list_edges,
    list_nodes,
    list_tasks,
    mark_task_resuming,
    request_cancel_task,
    request_pause_task,
    reset_task_for_retry,
    update_task_status,
)
from app.worker import run_analysis_task

router = APIRouter()


def _to_task_response(task) -> AnalysisTaskResponse:
    return AnalysisTaskResponse(
        id=task.id,
        user_input=task.user_input,
        topic=task.topic,
        industry=task.industry,
        target_product=task.target_product,
        status=task.status,
        report_depth=task.report_depth,
        output_language=task.output_language,
        task_plan=get_task_plan(task),
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _run_analysis_in_local_thread(task_id: int) -> None:
    def runner() -> None:
        from app.graph.workflow import TaskCanceled, TaskPaused, run_competitive_analysis
        from app.services.task_service import update_task_status

        db = SessionLocal()
        try:
            _console("local background task started", {"task_id": task_id})
            run_competitive_analysis(db, task_id)
            _console("local background task completed", {"task_id": task_id})
        except TaskPaused as exc:
            update_task_status(db, task_id, "paused", str(exc))
            _console("local background task paused", {"task_id": task_id})
        except TaskCanceled as exc:
            update_task_status(db, task_id, "canceled", str(exc))
            _console("local background task canceled", {"task_id": task_id})
        except Exception as exc:
            update_task_status(db, task_id, "failed", str(exc))
            _console("local background task failed", {"task_id": task_id, "error": str(exc)})
        finally:
            db.close()

    Thread(target=runner, daemon=True, name=f"analysis-task-{task_id}").start()


def _enqueue_or_run_task(db: Session, task_id: int) -> None:
    if settings.run_tasks_inline:
        from app.graph.workflow import run_competitive_analysis

        run_competitive_analysis(db, task_id)
        return

    worker_heartbeat = get_worker_heartbeat()
    if worker_heartbeat is None:
        message = "Celery Worker heartbeat missing; worker is not ready to consume tasks"
        _console("analysis task worker unavailable", {"task_id": task_id, "queue": CELERY_QUEUE_NAME})
        if settings.fallback_to_local_thread_when_worker_unavailable:
            update_task_status(db, task_id, "running")
            _console("falling back to local background thread", {"task_id": task_id, "reason": message})
            _run_analysis_in_local_thread(task_id)
            return
        update_task_status(db, task_id, "failed", message)
        raise HTTPException(status_code=503, detail=message)

    async_result = run_analysis_task.apply_async(args=[task_id], queue=CELERY_QUEUE_NAME, routing_key=CELERY_QUEUE_NAME)
    _console(
        "analysis task enqueued",
        {"task_id": task_id, "celery_task_id": async_result.id, "queue": CELERY_QUEUE_NAME, "worker": worker_heartbeat},
    )


def _normalize_qa_payload(qa_result) -> dict:
    payload = qa_result.issues_json or []
    base_payload = {
        "passed": qa_result.passed,
        "score": float(qa_result.score) if qa_result.score is not None else None,
    }
    if isinstance(payload, dict):
        return {
            **base_payload,
            "issues": payload.get("issues") or [],
            "next_action": payload.get("next_action") or "end",
            "target_nodes": payload.get("target_nodes") or [],
            "revision_reason": payload.get("revision_reason"),
            "revision_round": payload.get("revision_round") or 0,
        }
    return {
        **base_payload,
        "issues": payload if isinstance(payload, list) else [],
        "next_action": "end",
        "target_nodes": [],
        "revision_reason": None,
        "revision_round": 0,
    }


def _virtual_worker_status(parent_status: str) -> str:
    if parent_status in {"running", "success", "failed", "paused", "canceled"}:
        return parent_status
    return "pending"


def _with_parallel_worker_nodes(task_id: int, nodes: list, edges: list[dict]) -> tuple[list, list[dict]]:
    node_by_key = {node.node_key: node for node in nodes}
    next_nodes = list(nodes)
    next_edges = [dict(edge) for edge in edges if edge.get("source") not in {"collector", "evidence_extractor"} or edge.get("type") == "revision"]
    dimension_targets = [node.node_key for node in nodes if getattr(node, "node_type", None) == "dimension_analyst"]
    if not dimension_targets:
        dimension_targets = ["report_writer"]

    def add_workers(parent_key: str, worker_prefix: str, worker_name: str, worker_count: int, downstream_targets: list[str]) -> None:
        parent = node_by_key.get(parent_key)
        if parent is None:
            return
        parent_status = _virtual_worker_status(parent.status)
        base_id = 10_000_000 if worker_prefix == "collector_worker" else 20_000_000
        for index in range(1, max(1, worker_count) + 1):
            worker_key = f"{worker_prefix}_{index}"
            next_nodes.append(
                {
                    "id": -(base_id + task_id * 100 + index),
                    "task_id": task_id,
                    "node_key": worker_key,
                    "node_name": f"{worker_name} {index}",
                    "node_type": "virtual_worker",
                    "status": parent_status,
                    "input_summary": f"parallel worker of {parent_key}",
                    "output_summary": None,
                    "started_at": parent.started_at,
                    "ended_at": parent.ended_at,
                    "duration_ms": parent.duration_ms,
                    "retry_count": parent.retry_count,
                    "error_message": parent.error_message,
                }
            )
            next_edges.append({"source": parent_key, "target": worker_key, "type": "parallel", "label": "parallel"})
            for target in downstream_targets:
                next_edges.append({"source": worker_key, "target": target, "type": "parallel"})

    add_workers("collector", "collector_worker", "采集 Worker", settings.collector_max_workers, ["evidence_extractor"])
    add_workers(
        "evidence_extractor",
        "evidence_worker",
        "证据 Worker",
        settings.evidence_extractor_max_workers,
        dimension_targets,
    )
    return next_nodes, next_edges


@router.post("", response_model=AnalysisTaskCreateResponse)
def create_analysis_task(request: AnalysisTaskCreateRequest, db: Session = Depends(get_db)) -> AnalysisTaskCreateResponse:
    _console("analysis task create requested", {"topic": request.task_plan.topic, "competitors": request.task_plan.competitors})
    task = create_task(db, request)
    _console("analysis task created", {"task_id": task.id, "run_tasks_inline": settings.run_tasks_inline})
    try:
        _enqueue_or_run_task(db, task.id)
    except HTTPException:
        raise
    except Exception as exc:
        _console("analysis task enqueue failed", {"task_id": task.id, "error": str(exc)})
        if settings.fallback_to_local_thread_on_celery_error:
            update_task_status(db, task.id, "running")
            _console("falling back to local background thread", {"task_id": task.id})
            _run_analysis_in_local_thread(task.id)
        else:
            update_task_status(db, task.id, "failed", f"Celery enqueue failed: {exc}")
            raise HTTPException(status_code=503, detail=f"Celery/Redis enqueue failed: {exc}") from exc
    db.refresh(task)
    _console("analysis task create response", {"task_id": task.id, "status": task.status})
    return AnalysisTaskCreateResponse(task_id=task.id, status=task.status)


@router.get("", response_model=AnalysisTaskHistoryResponse)
def get_analysis_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AnalysisTaskHistoryResponse:
    items = []
    for task in list_tasks(db, limit=limit, offset=offset):
        task_response = _to_task_response(task)
        nodes = sorted(task.nodes, key=lambda node: node.id)
        items.append(AnalysisTaskHistoryItem(**task_response.model_dump(), nodes=nodes))
    return AnalysisTaskHistoryResponse(items=items)


@router.get("/{task_id}", response_model=AnalysisTaskResponse)
def get_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_task_response(task)


@router.post("/{task_id}/pause", response_model=AnalysisTaskResponse)
def pause_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = request_pause_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _console("analysis task pause requested", {"task_id": task_id, "status": task.status})
    return _to_task_response(task)


@router.post("/{task_id}/resume", response_model=AnalysisTaskResponse)
def resume_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = mark_task_resuming(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "queued":
        raise HTTPException(status_code=409, detail=f"Task cannot be resumed from status {task.status}")
    _enqueue_or_run_task(db, task_id)
    db.refresh(task)
    _console("analysis task resume requested", {"task_id": task_id, "status": task.status})
    return _to_task_response(task)


@router.post("/{task_id}/cancel", response_model=AnalysisTaskResponse)
def cancel_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = request_cancel_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _console("analysis task cancel requested", {"task_id": task_id, "status": task.status})
    return _to_task_response(task)


@router.post("/{task_id}/retry", response_model=AnalysisTaskResponse)
def retry_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in {"failed", "canceled", "paused", "success"}:
        raise HTTPException(status_code=409, detail=f"Task cannot be retried from status {task.status}")
    task = reset_task_for_retry(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _enqueue_or_run_task(db, task_id)
    db.refresh(task)
    _console("analysis task retry requested", {"task_id": task_id, "status": task.status})
    return _to_task_response(task)


@router.get("/{task_id}/nodes", response_model=AgentNodeListResponse)
def get_task_nodes(task_id: int, db: Session = Depends(get_db)) -> AgentNodeListResponse:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    nodes, edges = _with_parallel_worker_nodes(task_id, list_nodes(db, task_id), list_edges(db, task_id))
    return AgentNodeListResponse(nodes=nodes, edges=edges)


@router.get("/{task_id}/logs", response_model=AgentLogListResponse)
def get_task_logs(task_id: int, node_key: str | None = Query(default=None), db: Session = Depends(get_db)) -> AgentLogListResponse:
    logs = [
        AgentLogResponse(
            id=log.id,
            task_id=log.task_id,
            node_id=log.node_id,
            log_type=log.log_type,
            message=log.message,
            payload=log.payload_json,
            created_at=log.created_at,
        )
        for log in list_logs(db, task_id, node_key)
    ]
    return AgentLogListResponse(logs=logs)


@router.get("/{task_id}/evidence", response_model=EvidenceListResponse)
def get_task_evidence(
    task_id: int,
    competitor_name: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EvidenceListResponse:
    return EvidenceListResponse(items=list_evidence(db, task_id, competitor_name, source_type))


@router.get("/{task_id}/claims", response_model=ClaimListResponse)
def get_task_claims(task_id: int, db: Session = Depends(get_db)) -> ClaimListResponse:
    items = [
        ClaimItem(
            id=claim.id,
            task_id=claim.task_id,
            competitor_name=claim.competitor_name,
            claim_type=claim.claim_type,
            dimension_key=claim.dimension_key,
            dimension_label=claim.dimension_label,
            claim_text=claim.claim_text,
            confidence=claim.confidence,
            risk_level=claim.risk_level,
            evidence_ids=evidence_ids,
            created_at=claim.created_at,
        )
        for claim, evidence_ids in list_claims_with_evidence(db, task_id)
    ]
    return ClaimListResponse(items=items)


@router.get("/{task_id}/report", response_model=ReportResponse)
def get_task_report(task_id: int, db: Session = Depends(get_db)) -> ReportResponse:
    report = get_report(db, task_id)
    if report is None:
        return ReportResponse(report=None)
    claim_items = []
    evidence_ids: set[int] = set()
    for claim, claim_evidence_ids in list_claims_with_evidence(db, task_id):
        evidence_ids.update(claim_evidence_ids)
        claim_items.append(
            ReportClaimItem(
                id=claim.id,
                task_id=claim.task_id,
                claim_text=claim.claim_text,
                competitor_name=claim.competitor_name,
                claim_type=claim.claim_type,
                dimension_key=claim.dimension_key,
                dimension_label=claim.dimension_label,
                confidence=claim.confidence,
                risk_level=claim.risk_level,
                evidence_ids=claim_evidence_ids,
                created_at=claim.created_at,
            )
        )
    evidence_items = [
        ReportEvidenceItem(
            id=item.id,
            source_url=item.source_url,
            source_title=item.source_title,
            source_type=item.source_type,
            chunk_text=item.chunk_text,
            competitor_name=item.competitor_name,
            reliability_score=item.reliability_score,
        )
        for item in list_evidence(db, task_id)
        if item.id in evidence_ids
    ]
    qa_result = get_qa_result(db, task_id)
    profiles = list(db.scalars(select(CompetitorProfile).where(CompetitorProfile.task_id == task_id).order_by(CompetitorProfile.id)))
    matrices = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
    return ReportResponse(
        report=ReportItem(
            id=report.id,
            task_id=report.task_id,
            title=report.title,
            content_markdown=report.content_markdown,
            content_html=report.content_html,
            report_json=report.report_json,
            created_at=report.created_at,
            updated_at=report.updated_at,
        ),
        claims=claim_items,
        evidence=evidence_items,
        qa_result=_normalize_qa_payload(qa_result) if qa_result else None,
        profiles=[CompetitorProfileItem.model_validate(item) for item in profiles],
        matrices=[ComparisonMatrixItem.model_validate(item) for item in matrices],
    )


@router.get("/{task_id}/profiles", response_model=CompetitorProfileListResponse)
def get_task_profiles(task_id: int, db: Session = Depends(get_db)) -> CompetitorProfileListResponse:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    items = list(db.scalars(select(CompetitorProfile).where(CompetitorProfile.task_id == task_id).order_by(CompetitorProfile.id)))
    return CompetitorProfileListResponse(items=[CompetitorProfileItem.model_validate(item) for item in items])


@router.get("/{task_id}/matrices", response_model=ComparisonMatrixListResponse)
def get_task_matrices(task_id: int, db: Session = Depends(get_db)) -> ComparisonMatrixListResponse:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    items = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
    return ComparisonMatrixListResponse(items=[ComparisonMatrixItem.model_validate(item) for item in items])


@router.get("/{task_id}/metrics", response_model=TaskMetricsResponse)
def get_task_metrics(task_id: int, db: Session = Depends(get_db)) -> TaskMetricsResponse:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return MetricsService(db).build_metrics(task_id)


@router.get("/{task_id}/report/export")
def export_task_report(
    task_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|md|pdf)$"),
    db: Session = Depends(get_db),
) -> Response:
    report = get_report(db, task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    normalized_format = "markdown" if format in {"markdown", "md"} else "pdf"
    if normalized_format == "markdown":
        filename = safe_report_filename(report, "md")
        matrices = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
        qa_result = get_qa_result(db, task_id)
        claims_with_evidence = list_claims_with_evidence(db, task_id)
        body = build_markdown_export(
            report,
            matrices=matrices,
            qa_payload=_normalize_qa_payload(qa_result) if qa_result else None,
            claims_with_evidence=claims_with_evidence,
        ).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    else:
        filename = safe_report_filename(report, "pdf")
        try:
            matrices = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
            qa_result = get_qa_result(db, task_id)
            claims_with_evidence = list_claims_with_evidence(db, task_id)
            body = build_pdf_export(
                report,
                matrices=matrices,
                qa_payload=_normalize_qa_payload(qa_result) if qa_result else None,
                claims_with_evidence=claims_with_evidence,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        media_type = "application/pdf"

    quoted_filename = quote(filename)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}"},
    )


@router.get("/{task_id}/qa", response_model=QAResultResponse)
def get_task_qa(task_id: int, db: Session = Depends(get_db)) -> QAResultResponse:
    qa_result = get_qa_result(db, task_id)
    if qa_result is None:
        return QAResultResponse(qa_result=None)
    payload = _normalize_qa_payload(qa_result)
    return QAResultResponse(
        qa_result=QAResultItem(
            id=qa_result.id,
            task_id=qa_result.task_id,
            report_id=qa_result.report_id,
            passed=qa_result.passed,
            score=qa_result.score,
            issues=payload["issues"],
            next_action=payload["next_action"],
            target_nodes=payload["target_nodes"],
            revision_reason=payload["revision_reason"],
            revision_round=payload["revision_round"],
            created_at=qa_result.created_at,
        )
    )
