import type { ClaimItem } from './claim'
import type { ComparisonMatrix } from './comparisonMatrix'
import type { CompetitorProfile } from './competitorProfile'
import type { QAResult } from './qa'

export interface ReportParagraph {
  paragraph_id: string
  text: string
  claim_ids: number[]
  evidence_ids: number[]
}

export interface ReportSection {
  section_id: string
  title: string
  paragraphs: ReportParagraph[]
}

export interface ReportItem {
  id: number
  task_id: number
  title: string
  content_markdown: string
  content_html?: string | null
  report_json?: {
    title?: string
    sections?: ReportSection[]
    [key: string]: unknown
  } | null
  created_at: string
  updated_at: string
}

export interface ReportEvidenceItem {
  id: number
  source_url: string
  source_title?: string | null
  source_type?: string | null
  chunk_text: string
  competitor_name?: string | null
  reliability_score?: string | number | null
}

export interface ReportResponse {
  report: ReportItem | null
  claims: ClaimItem[]
  evidence: ReportEvidenceItem[]
  qa_result?: QAResult | null
  profiles?: CompetitorProfile[]
  matrices?: ComparisonMatrix[]
}
