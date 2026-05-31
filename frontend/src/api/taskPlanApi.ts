import { http } from './http'
import type { TaskPlan } from '@/types/taskPlan'

export async function parseTaskPlan(user_input: string, auto_discover_competitors = true): Promise<TaskPlan> {
  const { data } = await http.post<{ task_plan: TaskPlan }>('/task-plans/parse', {
    user_input,
    auto_discover_competitors,
  })
  return data.task_plan
}
