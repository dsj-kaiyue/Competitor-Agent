import type { TaskPlan } from './taskPlan'

export interface AnalysisTask {
  id: number
  user_input: string
  topic: string
  industry?: string | null
  target_product?: string | null
  status: string
  report_depth: string
  output_language: string
  task_plan: TaskPlan
  error_message?: string | null
  created_at: string
  updated_at: string
}
