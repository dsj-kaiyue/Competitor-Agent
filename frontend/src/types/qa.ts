export interface QAIssue {
  type: string
  severity: string
  message: string
  related_claim_id?: number | null
  related_competitor?: string | null
  related_dimension?: string | null
  suggested_action?: string
  suggested_action_label?: string
  target_node?: string | null
  target_node_label?: string | null
  search_query?: string | null
  type_label?: string
  severity_label?: string
}

export interface QAResult {
  id: number
  task_id: number
  report_id?: number | null
  passed: boolean
  score?: string | number | null
  issues: QAIssue[]
  next_action?: string
  next_action_label?: string
  target_nodes?: string[]
  target_node_labels?: string[]
  qa_scope?: string
  qa_scope_label?: string
  revision_reason?: string | null
  revision_round?: number
  created_at: string
}
