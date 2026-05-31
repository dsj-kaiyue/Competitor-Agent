export interface ProfileField {
  key: string
  label: string
  type: string
  required?: boolean
  description?: string
}

export interface ProfileFieldData {
  value: string | string[] | null
  claim_ids: number[]
  evidence_ids: number[]
  confidence: number
  missing_reason?: string
}

export interface CompetitorProfile {
  id: number
  task_id: number
  competitor_name: string
  template_key?: string | null
  profile_schema_json: {
    template_key?: string | null
    industry?: string | null
    fields: ProfileField[]
  }
  profile_data_json: Record<string, ProfileFieldData>
  claim_ids_json?: number[] | null
  evidence_ids_json?: number[] | null
  created_at: string
  updated_at: string
}
