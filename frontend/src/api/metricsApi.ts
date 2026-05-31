import { http } from './http'
import type { TaskMetrics } from '@/types/metrics'

export async function getTaskMetrics(taskId: number) {
  const { data } = await http.get<TaskMetrics>(`/analysis-tasks/${taskId}/metrics`)
  return data
}
