from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.graph.workflow import run_competitive_analysis
from app.schemas.agent_node import AgentLogListResponse, AgentLogResponse, AgentNodeListResponse
from app.schemas.analysis_task import AnalysisTaskCreateRequest, AnalysisTaskCreateResponse, AnalysisTaskResponse
from app.schemas.claim import ClaimItem, ClaimListResponse
from app.schemas.evidence import EvidenceListResponse
from app.schemas.qa import QAResultItem, QAResultResponse
from app.schemas.report import ReportItem, ReportResponse
from app.services.claim_service import list_claims_with_evidence
from app.services.evidence_service import list_evidence
from app.services.log_service import list_logs
from app.services.qa_service import get_qa_result
from app.services.report_service import get_report
from app.services.task_service import DAG_EDGES, create_task, get_task, get_task_plan, list_nodes
from app.worker import run_analysis_task

router = APIRouter()


@router.post("", response_model=AnalysisTaskCreateResponse)
def create_analysis_task(request: AnalysisTaskCreateRequest, db: Session = Depends(get_db)) -> AnalysisTaskCreateResponse:
    task = create_task(db, request)
    if settings.run_tasks_inline:
        run_competitive_analysis(db, task.id)
    else:
        run_analysis_task.delay(task.id)
    db.refresh(task)
    return AnalysisTaskCreateResponse(task_id=task.id, status=task.status)


@router.get("/{task_id}", response_model=AnalysisTaskResponse)
def get_analysis_task(task_id: int, db: Session = Depends(get_db)) -> AnalysisTaskResponse:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
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
