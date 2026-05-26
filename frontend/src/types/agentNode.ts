export interface AgentNode {
  id: number
  task_id: number
  node_key: string
  node_name: string
  node_type: string
  status: string
  input_summary?: string | null
  output_summary?: string | null
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  retry_count: number
  error_message?: string | null
}

export interface DagEdge {
  source: string
  target: string
  type?: string
  label?: string | null
}

export interface AgentLog {
  id: number
  task_id: number
  node_id?: number | null
  log_type: string
  message: string
  payload?: Record<string, unknown> | null
  created_at: string
}
