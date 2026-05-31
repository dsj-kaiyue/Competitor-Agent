<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import TaskPlanForm from '@/components/TaskPlanForm.vue'
import { createAnalysisTask } from '@/api/analysisTaskApi'
import { API_BASE_URL } from '@/api/http'
import { parseTaskPlan } from '@/api/taskPlanApi'
import type { TaskPlan } from '@/types/taskPlan'

const router = useRouter()
const demoInput =
  '请分析 Cursor、GitHub Copilot、Windsurf、Tabnine 在 AI 编程助手市场的竞品情况，重点关注产品定位、核心功能、Agent 能力、IDE 集成、价格策略、企业能力、安全合规和适用用户。'

const userInput = ref(demoInput)
const autoDiscoverCompetitors = ref(true)
const taskPlan = ref<TaskPlan | null>(null)
const parsing = ref(false)
const creating = ref(false)
const discovering = ref(false)
const lastError = ref('')
const loadingText = computed(() => {
  if (discovering.value) return '正在补充自动发现竞品...'
  if (parsing.value && autoDiscoverCompetitors.value) return '正在解析需求并自动发现竞品...'
  if (parsing.value) return '正在解析需求，生成 TaskPlan...'
  if (creating.value) return '正在提交后台分析任务...'
  return ''
})

function formatError(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      return `HTTP ${error.response.status}: ${JSON.stringify(error.response.data)}`
    }
    if (error.request) {
      return `无法连接 API：${error.message}。当前 API 地址：${API_BASE_URL}`
    }
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

async function handleParse() {
  parsing.value = true
  lastError.value = ''
  try {
    taskPlan.value = await parseTaskPlan(userInput.value, autoDiscoverCompetitors.value)
    const competitorCount = taskPlan.value.competitors.filter((name) => name.trim()).length
    ElMessage.success(autoDiscoverCompetitors.value ? `需求解析完成，已补充 ${competitorCount} 个竞品` : '需求解析完成')
  } catch (error) {
    console.error(error)
    lastError.value = formatError(error)
    ElMessage.error(`解析需求失败：${lastError.value}`)
  } finally {
    parsing.value = false
  }
}

function mergeCompetitors(existing: string[], discovered: string[]) {
  const names = new Set(existing.map((name) => name.trim().toLowerCase()).filter(Boolean))
  const merged = [...existing]
  for (const name of discovered) {
    const normalized = name.trim().toLowerCase()
    if (!normalized || names.has(normalized)) continue
    names.add(normalized)
    merged.push(name)
  }
  return merged
}

async function handleDiscoverCompetitors() {
  if (!taskPlan.value || discovering.value) return
  discovering.value = true
  lastError.value = ''
  try {
    const discoveredPlan = await parseTaskPlan(userInput.value, true)
    const before = taskPlan.value.competitors.filter((name) => name.trim()).length
    taskPlan.value.competitors = mergeCompetitors(taskPlan.value.competitors, discoveredPlan.competitors)
    const after = taskPlan.value.competitors.filter((name) => name.trim()).length
    ElMessage.success(`已补充 ${Math.max(0, after - before)} 个竞品`)
  } catch (error) {
    console.error(error)
    lastError.value = formatError(error)
    ElMessage.error(`自动发现竞品失败：${lastError.value}`)
  } finally {
    discovering.value = false
  }
}

async function handleCreate() {
  if (!taskPlan.value) return
  creating.value = true
  lastError.value = ''
  try {
    const result = await createAnalysisTask(userInput.value, taskPlan.value)
    ElMessage.success('分析任务已创建')
    await router.push(`/tasks/${result.task_id}`)
  } catch (error) {
    console.error(error)
    lastError.value = formatError(error)
    ElMessage.error(`创建分析任务失败：${lastError.value}`)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <main v-loading="parsing || creating || discovering" :element-loading-text="loadingText" class="page">
    <section class="toolbar">
      <div>
        <h1>竞品分析 Agent 工作台</h1>
        <p>从一句话输入生成 TaskPlan，并执行可观测的多 Agent DAG。</p>
        <p class="api-base">API：{{ API_BASE_URL }}</p>
      </div>
      <div class="actions">
        <RouterLink to="/history">
          <el-button>历史记录</el-button>
        </RouterLink>
        <el-switch
          v-model="autoDiscoverCompetitors"
          active-text="自动发现竞品"
          :disabled="parsing || creating || discovering"
        />
        <el-button type="primary" :loading="parsing" :disabled="creating || discovering" @click="handleParse">
          解析需求
        </el-button>
      </div>
    </section>

    <el-input v-model="userInput" type="textarea" :rows="5" resize="none" />

    <el-alert v-if="lastError" :title="lastError" type="error" show-icon :closable="false" />

    <section v-if="taskPlan" class="section">
      <div class="section-header">
        <h2>高级配置</h2>
        <el-button type="success" :loading="creating" :disabled="parsing || discovering" @click="handleCreate">
          开始分析
        </el-button>
      </div>
      <TaskPlanForm v-model="taskPlan" @request-discover="handleDiscoverCompetitors" />
    </section>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  gap: 20px;
}

.toolbar,
.section-header,
.actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar,
.section-header {
  justify-content: space-between;
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

.api-base {
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.section {
  display: grid;
  gap: 16px;
}
</style>
