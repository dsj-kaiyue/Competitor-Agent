export interface ReportItem {
  id: number
  task_id: number
  title: string
  content_markdown: string
  content_html?: string | null
  created_at: string
  updated_at: string
}
