export interface TaskPlan {
  topic: string
  industry?: string | null
  target_product?: string | null
  competitors: string[]
  analysis_dimensions: string[]
  report_depth: 'simple' | 'standard' | 'deep' | string
  output_language: string
  auto_discover_competitors: boolean
  data_sources: string[]
}
