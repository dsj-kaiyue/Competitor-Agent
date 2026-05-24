from typing import Any, TypedDict


class CompetitiveAnalysisState(TypedDict, total=False):
    task_id: int
    user_input: str
    task_plan: dict[str, Any]
    competitors: list[str]
    analysis_dimensions: list[str]
    source_document_ids: list[int]
    evidence_chunk_ids: list[int]
    claim_ids: list[int]
    report_id: int
    qa_result_id: int
    current_node: str
    errors: list[str]
