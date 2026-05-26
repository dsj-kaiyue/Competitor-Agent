export interface QAIssue {
  type: string
  severity: string
  message: string
  related_claim_id?: number | null
  related_competitor?: string | null
  related_dimension?: string | null
  suggested_action?: string
  target_node?: string | null
  search_query?: string | null
}

export interface QAResult {
  id: number
  task_id: number
  report_id?: number | null
  passed: boolean
  score?: string | number | null
  issues: QAIssue[]
  next_action?: string
  target_nodes?: string[]
  revision_reason?: string | null
  revision_round?: number
  created_at: string
}
