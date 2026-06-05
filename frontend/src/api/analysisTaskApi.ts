import { http } from './http'
import type { AgentLog, AgentNode, DagEdge } from '@/types/agentNode'
import type { AnalysisTask, AnalysisTaskHistoryItem } from '@/types/analysisTask'
import type { ClaimItem } from '@/types/claim'
import type { EvidenceItem } from '@/types/evidence'
import type { QAResult } from '@/types/qa'
import type { ReportItem, ReportResponse } from '@/types/report'
import type { TaskPlan } from '@/types/taskPlan'
import type { TaskMetrics } from '@/types/metrics'

export async function createAnalysisTask(user_input: string, task_plan: TaskPlan) {
  const { data } = await http.post<{ task_id: number; status: string }>('/analysis-tasks', {
    user_input,
    task_plan,
  })
  return data
}

export async function getAnalysisTasks(params?: { limit?: number; offset?: number; user_id?: number }) {
  const { data } = await http.get<{ items: AnalysisTaskHistoryItem[] }>('/analysis-tasks', {
    params,
  })
  return data.items
}

export async function getAnalysisTask(taskId: number) {
  const { data } = await http.get<AnalysisTask>(`/analysis-tasks/${taskId}`)
  return data
}

export async function pauseAnalysisTask(taskId: number) {
  const { data } = await http.post<AnalysisTask>(`/analysis-tasks/${taskId}/pause`)
  return data
}

export async function resumeAnalysisTask(taskId: number) {
  const { data } = await http.post<AnalysisTask>(`/analysis-tasks/${taskId}/resume`)
  return data
}

export async function cancelAnalysisTask(taskId: number) {
  const { data } = await http.post<AnalysisTask>(`/analysis-tasks/${taskId}/cancel`)
  return data
}

export async function retryAnalysisTask(taskId: number) {
  const { data } = await http.post<AnalysisTask>(`/analysis-tasks/${taskId}/retry`)
  return data
}

export async function getTaskNodes(taskId: number) {
  const { data } = await http.get<{ nodes: AgentNode[]; edges: DagEdge[] }>(
    `/analysis-tasks/${taskId}/nodes`,
  )
  return data
}

export async function getTaskLogs(taskId: number) {
  const { data } = await http.get<{ logs: AgentLog[] }>(`/analysis-tasks/${taskId}/logs`)
  return data.logs
}

export async function getTaskEvidence(taskId: number, params?: Record<string, string>) {
  const { data } = await http.get<{ items: EvidenceItem[] }>(`/analysis-tasks/${taskId}/evidence`, {
    params,
  })
  return data.items
}

export async function getTaskClaims(taskId: number) {
  const { data } = await http.get<{ items: ClaimItem[] }>(`/analysis-tasks/${taskId}/claims`)
  return data.items
}

export async function getTaskReport(taskId: number) {
  const { data } = await http.get<{ report: ReportItem | null }>(`/analysis-tasks/${taskId}/report`)
  return data.report
}

export async function getTaskReportDetail(taskId: number) {
  const { data } = await http.get<ReportResponse>(`/analysis-tasks/${taskId}/report`)
  return data
}

function filenameFromDisposition(disposition?: string): string | null {
  if (!disposition) {
    return null
  }
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i)
  return asciiMatch?.[1] || null
}

export async function downloadTaskReport(taskId: number, format: 'markdown' | 'pdf') {
  const { data, headers } = await http.get<Blob>(`/analysis-tasks/${taskId}/report/export`, {
    params: { format },
    responseType: 'blob',
  })
  const filename = filenameFromDisposition(headers['content-disposition']) || `analysis-report.${format === 'pdf' ? 'pdf' : 'md'}`
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export async function getTaskQa(taskId: number) {
  const { data } = await http.get<{ qa_result: QAResult | null }>(`/analysis-tasks/${taskId}/qa`)
  return data.qa_result
}

export async function getTaskQaHistory(taskId: number) {
  const { data } = await http.get<{ items: QAResult[] }>(`/analysis-tasks/${taskId}/qa/history`)
  return data.items
}

export async function getTaskMetrics(taskId: number) {
  const { data } = await http.get<TaskMetrics>(`/analysis-tasks/${taskId}/metrics`)
  return data
}
