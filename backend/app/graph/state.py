from typing import Any, TypedDict


class CompetitiveAnalysisState(TypedDict, total=False):
    task_id: int
    user_input: str
    task_plan: dict[str, Any]
    competitors: list[str]
    analysis_dimensions: list[str]
    dimension_prompt_specs: dict[str, dict[str, Any]]
    source_document_ids: list[int]
    evidence_chunk_ids: list[int]
    claim_ids: list[int]
    report_id: int
    report_writer_mode: str
    qa_result_id: int
    revision_round: int
    max_revision_rounds: int
    qa_passed: bool | None
    qa_next_action: str | None
    qa_target_nodes: list[str]
    qa_revision_plan: dict[str, Any]
    qa_issues: list[dict[str, Any]]
    qa_followup_queries: list[str]
    dimension_qa_scores: dict[str, dict[str, Any]]
    finalizer_qa: dict[str, Any]
    finalizer_revision_context: dict[str, Any]
    quality_summary: dict[str, Any]
    reanalyze_dimensions: list[str]
    dimension_failures: list[dict[str, Any]]
    current_node: str
    errors: list[str]
