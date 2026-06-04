import type { ClaimItem } from './claim'
import type { ComparisonMatrix } from './comparisonMatrix'
import type { CompetitorProfile } from './competitorProfile'
import type { DimensionQAScore, QAResult } from './qa'

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

export interface ReportQualitySummary {
  dimension_body_qa_status?: string
  finalizer_grounding_status?: string
  final_status?: string
  final_score?: number | string | null
  dimension_avg?: number | string | null
  finalizer_score?: number | string | null
  dimension_weight?: number
  finalizer_weight?: number
  dimension_pass_threshold?: number
  finalizer_pass_threshold?: number
  high_risk_issue_count?: number
  blockers?: string[]
}

export interface ReportFinalizerQa {
  passed?: boolean
  score?: number | string | null
  issues?: Record<string, unknown>[]
  revision_round?: number
  pass_threshold?: number | string | null
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
    quality_summary?: ReportQualitySummary
    dimension_qa_scores?: DimensionQAScore[]
    finalizer_qa?: ReportFinalizerQa
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
