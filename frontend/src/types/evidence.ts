export interface EvidenceItem {
  id: number
  task_id: number
  competitor_name?: string | null
  source_url: string
  source_title?: string | null
  source_type?: string | null
  chunk_index: number
  chunk_text: string
  reliability_score?: string | number | null
  created_at: string
}
