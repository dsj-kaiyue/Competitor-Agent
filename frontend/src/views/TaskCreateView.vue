<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import TaskPlanForm from '@/components/TaskPlanForm.vue'
import { createAnalysisTask } from '@/api/analysisTaskApi'
import { parseTaskPlan } from '@/api/taskPlanApi'
import type { TaskPlan } from '@/types/taskPlan'

const router = useRouter()
const demoInput =
  '请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。'

const userInput = ref(demoInput)
const taskPlan = ref<TaskPlan | null>(null)
const parsing = ref(false)
const creating = ref(false)

async function handleParse() {
  parsing.value = true
  try {
    taskPlan.value = await parseTaskPlan(userInput.value)
    ElMessage.success('需求解析完成')
  } finally {
    parsing.value = false
  }
}

async function handleCreate() {
  if (!taskPlan.value) return
  creating.value = true
  try {
    const result = await createAnalysisTask(userInput.value, taskPlan.value)
    ElMessage.success('分析任务已创建')
    await router.push(`/tasks/${result.task_id}`)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>竞品分析 Agent 工作台</h1>
        <p>从一句话输入生成 TaskPlan，并执行可观测的多 Agent DAG。</p>
      </div>
      <el-button type="primary" :loading="parsing" @click="handleParse">解析需求</el-button>
    </section>

    <el-input v-model="userInput" type="textarea" :rows="5" resize="none" />

    <section v-if="taskPlan" class="section">
      <div class="section-header">
        <h2>高级配置</h2>
        <el-button type="success" :loading="creating" @click="handleCreate">开始分析</el-button>
      </div>
      <TaskPlanForm v-model="taskPlan" />
    </section>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  gap: 20px;
}

.toolbar,
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 24px;
}

h2 {
  font-size: 18px;
}

p {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}

.section {
  display: grid;
  gap: 16px;
}
</style>
