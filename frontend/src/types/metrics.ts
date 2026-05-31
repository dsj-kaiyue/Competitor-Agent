export interface TaskMetrics {
  task_id: number
  status: string
  total_duration_ms?: number | null
  source_document_count: number
  evidence_chunk_count: number
  embedded_chunk_count: number
  embedding_failed_count: number
  claim_count: number
  claim_with_evidence_count: number
  evidence_coverage: number
  used_evidence_count: number
  evidence_usage_rate: number
  profile_count: number
  matrix_count: number
  qa_score?: number | null
  qa_passed?: boolean | null
  revision_count: number
  source_diversity: Record<string, number>
  competitor_coverage: Record<string, Record<string, unknown>>
  rag_query_count: number
  rag_fallback_count: number
  external_error_count: number
  node_durations: Array<{
    node_key: string
    node_name: string
    status: string
    duration_ms?: number | null
  }>
}
