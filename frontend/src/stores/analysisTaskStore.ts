import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TaskPlan } from '@/types/taskPlan'

export const useAnalysisTaskStore = defineStore('analysis-task', () => {
  const taskPlan = ref<TaskPlan | null>(null)
  const currentTaskId = ref<number | null>(null)

  return { taskPlan, currentTaskId }
})
