import { http } from './http'
import type { AgentLog, AgentNode, DagEdge } from '@/types/agentNode'
import type { AnalysisTask, AnalysisTaskHistoryItem } from '@/types/analysisTask'
import type { ClaimItem } from '@/types/claim'
import type { EvidenceItem } from '@/types/evidence'
import type { QAResult } from '@/types/qa'
import type { ReportItem } from '@/types/report'
import type { TaskPlan } from '@/types/taskPlan'

export async function createAnalysisTask(user_input: string, task_plan: TaskPlan) {
  const { data } = await http.post<{ task_id: number; status: string }>('/analysis-tasks', {
    user_input,
    task_plan,
  })
  return data
}

export async function getAnalysisTasks(params?: { limit?: number; offset?: number }) {
  const { data } = await http.get<{ items: AnalysisTaskHistoryItem[] }>('/analysis-tasks', {
    params,
  })
  return data.items
}

export async function getAnalysisTask(taskId: number) {
  const { data } = await http.get<AnalysisTask>(`/analysis-tasks/${taskId}`)
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

export async function getTaskQa(taskId: number) {
  const { data } = await http.get<{ qa_result: QAResult | null }>(`/analysis-tasks/${taskId}/qa`)
  return data.qa_result
}
