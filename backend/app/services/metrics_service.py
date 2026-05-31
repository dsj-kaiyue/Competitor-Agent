from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.agent_node import AgentNode
from app.models.agent_run_log import AgentRunLog
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.comparison_matrix import ComparisonMatrix
from app.models.competitor_profile import CompetitorProfile
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.source_document import SourceDocument
from app.schemas.metrics import TaskMetricsResponse
from app.services.task_service import get_task_plan


class MetricsService:
    def __init__(self, db: Session):
        self.db = db

    def build_metrics(self, task_id: int) -> TaskMetricsResponse:
        task = self.db.get(AnalysisTask, task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} not found")

        source_document_count = self._count(SourceDocument, task_id)
        evidence_chunk_count = self._count(EvidenceChunk, task_id)
        embedded_chunk_count = self._scalar(
            select(func.count())
            .select_from(EvidenceChunk)
            .where(
                EvidenceChunk.task_id == task_id,
                EvidenceChunk.milvus_vector_id.is_not(None),
                ~EvidenceChunk.milvus_vector_id.like("embedding-failed-%"),
            )
        )
        embedding_failed_count = self._scalar(
            select(func.count())
            .select_from(EvidenceChunk)
            .where(EvidenceChunk.task_id == task_id, EvidenceChunk.milvus_vector_id.like("embedding-failed-%"))
        )
        claim_count = self._count(Claim, task_id)
        claim_with_evidence_count = self._scalar(
            select(func.count(distinct(ClaimEvidence.claim_id)))
            .select_from(ClaimEvidence)
            .join(Claim, Claim.id == ClaimEvidence.claim_id)
            .where(Claim.task_id == task_id)
        )
        used_evidence_count = self._scalar(
            select(func.count(distinct(ClaimEvidence.evidence_chunk_id)))
            .select_from(ClaimEvidence)
            .join(EvidenceChunk, EvidenceChunk.id == ClaimEvidence.evidence_chunk_id)
            .where(EvidenceChunk.task_id == task_id)
        )
        profile_count = self._count(CompetitorProfile, task_id)
        matrix_count = self._count(ComparisonMatrix, task_id)
        latest_qa = self.db.scalar(select(QAResult).where(QAResult.task_id == task_id).order_by(QAResult.id.desc()))
        qa_results = list(self.db.scalars(select(QAResult).where(QAResult.task_id == task_id)))
        nodes = list(self.db.scalars(select(AgentNode).where(AgentNode.task_id == task_id).order_by(AgentNode.id)))
        logs = list(self.db.scalars(select(AgentRunLog).where(AgentRunLog.task_id == task_id)))

        source_diversity = self._source_diversity(task_id)
        competitor_coverage = self._competitor_coverage(task_id)
        rag_query_count = 0
        rag_fallback_count = 0
        external_error_count = 0
        for log in logs:
            payload = log.payload_json or {}
            if payload.get("retrieval_mode") == "milvus_rag":
                rag_query_count += 1
            if payload.get("retrieval_mode") == "mysql_fallback" or payload.get("fallback_used"):
                rag_fallback_count += 1
            if log.log_type == "error":
                external_error_count += 1

        node_durations = [
            {
                "node_key": node.node_key,
                "node_name": node.node_name,
                "status": node.status,
                "duration_ms": node.duration_ms,
            }
            for node in nodes
        ]
        completed_durations = [node.duration_ms or 0 for node in nodes if node.duration_ms]

        return TaskMetricsResponse(
            task_id=task_id,
            status=task.status,
            total_duration_ms=sum(completed_durations) if completed_durations else None,
            source_document_count=source_document_count,
            evidence_chunk_count=evidence_chunk_count,
            embedded_chunk_count=embedded_chunk_count,
            embedding_failed_count=embedding_failed_count,
            claim_count=claim_count,
            claim_with_evidence_count=claim_with_evidence_count,
            evidence_coverage=round(claim_with_evidence_count / claim_count, 4) if claim_count else 0.0,
            used_evidence_count=used_evidence_count,
            evidence_usage_rate=round(used_evidence_count / evidence_chunk_count, 4) if evidence_chunk_count else 0.0,
            profile_count=profile_count,
            matrix_count=matrix_count,
            qa_score=float(latest_qa.score) if latest_qa and latest_qa.score is not None else None,
            qa_passed=latest_qa.passed if latest_qa else None,
            revision_count=max(0, len(qa_results) - 1),
            source_diversity=source_diversity,
            competitor_coverage=competitor_coverage,
            rag_query_count=rag_query_count,
            rag_fallback_count=rag_fallback_count,
            external_error_count=external_error_count,
            node_durations=node_durations,
        )

    def _count(self, model, task_id: int) -> int:
        return self._scalar(select(func.count()).select_from(model).where(model.task_id == task_id))

    def _scalar(self, stmt) -> int:
        return int(self.db.scalar(stmt) or 0)

    def _source_diversity(self, task_id: int) -> dict[str, int]:
        rows = self.db.execute(
            select(EvidenceChunk.source_type, func.count())
            .where(EvidenceChunk.task_id == task_id)
            .group_by(EvidenceChunk.source_type)
        )
        return {str(source_type or "unknown"): int(count) for source_type, count in rows}

    def _competitor_coverage(self, task_id: int) -> dict[str, dict]:
        task = self.db.get(AnalysisTask, task_id)
        plan = get_task_plan(task) if task else None
        competitors = plan.competitors if plan else []
        result: dict[str, dict] = {}
        for competitor in competitors:
            chunks = list(
                self.db.scalars(
                    select(EvidenceChunk).where(
                        EvidenceChunk.task_id == task_id,
                        EvidenceChunk.competitor_name == competitor,
                    )
                )
            )
            source_types = {chunk.source_type or "unknown" for chunk in chunks}
            source_urls = {chunk.source_url for chunk in chunks}
            checks = {
                "official_website": "official_website" in source_types,
                "pricing_page": "pricing_page" in source_types,
                "docs": "docs" in source_types,
                "security_or_enterprise": bool(source_types & {"security", "enterprise"}),
                "third_party": bool(source_types & {"blog", "news", "reviews", "third_party"}),
            }
            result[competitor] = {
                "source_count": len(source_urls),
                "evidence_count": len(chunks),
                **checks,
                "coverage_score": round(sum(1 for value in checks.values() if value) / len(checks), 2),
            }
        return result
