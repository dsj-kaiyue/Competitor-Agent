import { http } from './http'
import type { CompetitorProfile } from '@/types/competitorProfile'

export async function getTaskProfiles(taskId: number) {
  const { data } = await http.get<{ items: CompetitorProfile[] }>(`/analysis-tasks/${taskId}/profiles`)
  return data.items
}
