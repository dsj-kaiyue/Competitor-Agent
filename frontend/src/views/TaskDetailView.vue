<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import DagFlow from '@/components/DagFlow.vue'
import { getAnalysisTask, getTaskLogs, getTaskNodes } from '@/api/analysisTaskApi'
import type { AgentLog, AgentNode, DagEdge } from '@/types/agentNode'
import type { AnalysisTask } from '@/types/analysisTask'

const route = useRoute()
const taskId = Number(route.params.id)
const task = ref<AnalysisTask | null>(null)
const nodes = ref<AgentNode[]>([])
const edges = ref<DagEdge[]>([])
const logs = ref<AgentLog[]>([])
let timer: number | undefined

async function load() {
  task.value = await getAnalysisTask(taskId)
  const flow = await getTaskNodes(taskId)
  nodes.value = flow.nodes
  edges.value = flow.edges
  logs.value = await getTaskLogs(taskId)
}

onMounted(async () => {
  await load()
  timer = window.setInterval(load, 5000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>{{ task?.topic || '任务详情' }}</h1>
        <p>任务 #{{ taskId }} · {{ task?.status }}</p>
      </div>
      <div class="actions">
        <RouterLink :to="`/tasks/${taskId}/evidence`">
          <el-button>证据链</el-button>
        </RouterLink>
        <RouterLink :to="`/tasks/${taskId}/report`">
          <el-button type="primary">报告</el-button>
        </RouterLink>
      </div>
    </section>

    <DagFlow :nodes="nodes" :edges="edges" />

    <section class="section">
      <h2>Agent 日志</h2>
      <el-timeline>
        <el-timeline-item
          v-for="log in logs"
          :key="log.id"
          :timestamp="log.created_at"
          :type="log.log_type === 'error' ? 'danger' : 'primary'"
        >
          {{ log.message }}
        </el-timeline-item>
      </el-timeline>
    </section>
  </main>
</template>

<style scoped>
.page,
.section {
  display: grid;
  gap: 18px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.actions {
  display: flex;
  gap: 10px;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 22px;
}

h2 {
  font-size: 18px;
}

p {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}
</style>
