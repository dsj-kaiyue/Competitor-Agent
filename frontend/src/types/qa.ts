export interface QAIssue {
  type: string
  severity: string
  message: string
  related_claim_id?: number | null
  suggested_action?: string
}

export interface QAResult {
  id: number
  task_id: number
  report_id?: number | null
  passed: boolean
  score?: string | number | null
  issues: QAIssue[]
  created_at: string
}
