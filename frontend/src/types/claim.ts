export interface ClaimItem {
  id: number
  task_id: number
  competitor_name?: string | null
  claim_type?: string | null
  dimension_key?: string | null
  dimension_label?: string | null
  claim_text: string
  confidence?: string | number | null
  risk_level?: string | null
  evidence_ids: number[]
  created_at: string
}
