from threading import Thread

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.schemas.qa import QAResultItem, QAResultResponse
from app.schemas.report import ReportItem, ReportResponse
from app.services.claim_service import list_claims_with_evidence
from app.services.evidence_service import list_evidence
from app.services.log_service import list_logs
from app.services.qa_service import get_qa_result
from app.services.report_service import get_report
from app.services.task_service import DAG_EDGES, create_task, get_task, get_task_plan, list_nodes, list_tasks, update_task_status
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
        from app.graph.workflow import run_competitive_analysis
        from app.services.task_service import update_task_status

        db = SessionLocal()
        try:
            _console("local background task started", {"task_id": task_id})
            run_competitive_analysis(db, task_id)
            _console("local background task completed", {"task_id": task_id})
        except Exception as exc:
            update_task_status(db, task_id, "failed", str(exc))
            _console("local background task failed", {"task_id": task_id, "error": str(exc)})
        finally:
            db.close()

    Thread(target=runner, daemon=True, name=f"analysis-task-{task_id}").start()


@router.post("", response_model=AnalysisTaskCreateResponse)
def create_analysis_task(request: AnalysisTaskCreateRequest, db: Session = Depends(get_db)) -> AnalysisTaskCreateResponse:
    _console("analysis task create requested", {"topic": request.task_plan.topic, "competitors": request.task_plan.competitors})
    task = create_task(db, request)
    _console("analysis task created", {"task_id": task.id, "run_tasks_inline": settings.run_tasks_inline})
    if settings.run_tasks_inline:
        from app.graph.workflow import run_competitive_analysis

        run_competitive_analysis(db, task.id)
    else:
        try:
            worker_heartbeat = get_worker_heartbeat()
            if worker_heartbeat is None:
                message = "Celery Worker heartbeat missing; worker is not ready to consume tasks"
                _console("analysis task worker unavailable", {"task_id": task.id, "queue": CELERY_QUEUE_NAME})
                if settings.fallback_to_local_thread_when_worker_unavailable:
                    update_task_status(db, task.id, "running")
                    _console("falling back to local background thread", {"task_id": task.id, "reason": message})
                    _run_analysis_in_local_thread(task.id)
                else:
                    update_task_status(db, task.id, "failed", message)
                    raise HTTPException(status_code=503, detail=message)
            else:
                async_result = run_analysis_task.apply_async(args=[task.id], queue=CELERY_QUEUE_NAME, routing_key=CELERY_QUEUE_NAME)
                _console(
                    "analysis task enqueued",
                    {"task_id": task.id, "celery_task_id": async_result.id, "queue": CELERY_QUEUE_NAME, "worker": worker_heartbeat},
                )
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


@router.get("/{task_id}/nodes", response_model=AgentNodeListResponse)
def get_task_nodes(task_id: int, db: Session = Depends(get_db)) -> AgentNodeListResponse:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return AgentNodeListResponse(nodes=list_nodes(db, task_id), edges=DAG_EDGES)


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
    return ReportResponse(
        report=ReportItem(
            id=report.id,
            task_id=report.task_id,
            title=report.title,
            content_markdown=report.content_markdown,
            content_html=report.content_html,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )
    )


@router.get("/{task_id}/qa", response_model=QAResultResponse)
def get_task_qa(task_id: int, db: Session = Depends(get_db)) -> QAResultResponse:
    qa_result = get_qa_result(db, task_id)
    if qa_result is None:
        return QAResultResponse(qa_result=None)
    return QAResultResponse(
        qa_result=QAResultItem(
            id=qa_result.id,
            task_id=qa_result.task_id,
            report_id=qa_result.report_id,
            passed=qa_result.passed,
            score=qa_result.score,
            issues=qa_result.issues_json or [],
            created_at=qa_result.created_at,
        )
    )
