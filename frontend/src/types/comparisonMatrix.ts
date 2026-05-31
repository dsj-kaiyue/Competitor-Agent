export interface MatrixValue {
  summary: string | string[] | null
  claim_ids: number[]
  evidence_ids: number[]
  confidence: number
}

export interface MatrixRow {
  key: string
  label: string
  values: Record<string, MatrixValue>
}

export interface ComparisonMatrix {
  id: number
  task_id: number
  template_key?: string | null
  matrix_type: string
  title: string
  matrix_schema_json: {
    template_key?: string | null
    columns: string[]
    rows: Array<{ key: string; label: string }>
  }
  matrix_data_json: {
    rows: MatrixRow[]
  }
  claim_ids_json?: number[] | null
  evidence_ids_json?: number[] | null
  created_at: string
  updated_at: string
}
