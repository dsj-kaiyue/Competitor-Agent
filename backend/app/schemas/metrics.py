from pydantic import BaseModel


class TaskMetricsResponse(BaseModel):
    task_id: int
    status: str
    total_duration_ms: int | None = None
    source_document_count: int = 0
    evidence_chunk_count: int = 0
    embedded_chunk_count: int = 0
    embedding_failed_count: int = 0
    claim_count: int = 0
    claim_with_evidence_count: int = 0
    evidence_coverage: float = 0.0
    used_evidence_count: int = 0
    evidence_usage_rate: float = 0.0
    profile_count: int = 0
    matrix_count: int = 0
    qa_score: float | None = None
    qa_passed: bool | None = None
    revision_count: int = 0
    source_diversity: dict[str, int] = {}
    competitor_coverage: dict[str, dict] = {}
    rag_query_count: int = 0
    rag_fallback_count: int = 0
    external_error_count: int = 0
    node_durations: list[dict] = []
