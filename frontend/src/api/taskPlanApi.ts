import { http } from './http'
import type { TaskPlan } from '@/types/taskPlan'

export async function parseTaskPlan(user_input: string): Promise<TaskPlan> {
  const { data } = await http.post<{ task_plan: TaskPlan }>('/task-plans/parse', { user_input })
  return data.task_plan
}
