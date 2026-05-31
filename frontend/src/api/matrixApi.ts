import { http } from './http'
import type { ComparisonMatrix } from '@/types/comparisonMatrix'

export async function getTaskMatrices(taskId: number) {
  const { data } = await http.get<{ items: ComparisonMatrix[] }>(`/analysis-tasks/${taskId}/matrices`)
  return data.items
}
