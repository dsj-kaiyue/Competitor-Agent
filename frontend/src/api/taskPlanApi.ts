import { http } from './http'
import type { TaskPlan } from '@/types/taskPlan'

export async function parseTaskPlan(
  user_input: string,
  auto_discover_competitors = false,
  auto_add_analysis_dimensions = false,
): Promise<TaskPlan> {
  const { data } = await http.post<{ task_plan: TaskPlan }>('/task-plans/parse', {
    user_input,
    auto_discover_competitors,
    auto_add_analysis_dimensions,
  })
  return data.task_plan
}
