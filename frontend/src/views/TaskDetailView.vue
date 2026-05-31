<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DagFlow from '@/components/DagFlow.vue'
import TaskMetricsPanel from '@/components/TaskMetricsPanel.vue'
import {
  cancelAnalysisTask,
  getAnalysisTask,
  getTaskMetrics,
  getTaskLogs,
  getTaskNodes,
  pauseAnalysisTask,
  resumeAnalysisTask,
  retryAnalysisTask,
} from '@/api/analysisTaskApi'
import type { AgentLog, AgentNode, DagEdge } from '@/types/agentNode'
import type { AnalysisTask } from '@/types/analysisTask'
import type { TaskMetrics } from '@/types/metrics'

const route = useRoute()
const taskId = Number(route.params.id)
const task = ref<AnalysisTask | null>(null)
const nodes = ref<AgentNode[]>([])
const edges = ref<DagEdge[]>([])
const logs = ref<AgentLog[]>([])
const metrics = ref<TaskMetrics | null>(null)
const activeLogGroups = ref<string[]>([])
const knownLogGroupKeys = ref(new Set<string>())
const controlLoading = ref<string | null>(null)
let timer: number | undefined

interface AgentLogGroup {
  key: string
  nodeName: string
  nodeStatus: string
  latestAt: string
  logs: AgentLog[]
}

const orderedNodeKeys = [
  'planner',
  'collector',
  'evidence_extractor',
  'feature_analysis',
  'pricing_analysis',
  'market_analysis',
  'security_analysis',
  'report_writer',
  'qa',
]

const currentNode = computed(() => nodes.value.find((node) => node.status === 'running'))
const completedCount = computed(() => nodes.value.filter((node) => node.status === 'success').length)
const canPause = computed(() =>
  ['queued', 'running', 'planned', 'collecting', 'extracting', 'analyzing', 'writing', 'qa_checking'].includes(
    task.value?.status || '',
  ),
)
const canResume = computed(() => ['paused', 'pause_requested'].includes(task.value?.status || ''))
const canCancel = computed(() =>
  ['queued', 'running', 'planned', 'collecting', 'extracting', 'analyzing', 'writing', 'qa_checking', 'pause_requested', 'paused'].includes(
    task.value?.status || '',
  ),
)
const canRetry = computed(() => ['failed', 'canceled', 'paused', 'success'].includes(task.value?.status || ''))
const progress = computed(() => {
  if (!nodes.value.length) return 0
  return Math.round((completedCount.value / nodes.value.length) * 100)
})
const statusType = computed(() => {
  if (task.value?.status === 'success') return 'success'
  if (['failed', 'canceled'].includes(task.value?.status || '')) return 'danger'
  if (task.value?.status === 'queued') return 'warning'
  if (['paused', 'pause_requested', 'cancel_requested'].includes(task.value?.status || '')) return 'warning'
  return 'primary'
})
const nodeById = computed(() => new Map(nodes.value.map((node) => [node.id, node])))
const sortedLogs = computed(() =>
  [...logs.value].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  ),
)
const groupedLogs = computed<AgentLogGroup[]>(() => {
  const groups = new Map<string, AgentLogGroup>()
  for (const log of sortedLogs.value) {
    const node = log.node_id ? nodeById.value.get(log.node_id) : undefined
    const key = node ? String(node.id) : 'system'
    const group = groups.get(key)
    if (group) {
      group.logs.push(log)
      continue
    }
    groups.set(key, {
      key,
      nodeName: node?.node_name || '系统日志',
      nodeStatus: node?.status || 'info',
      latestAt: log.created_at,
      logs: [log],
    })
  }
  return [...groups.values()].sort(
    (a, b) => new Date(b.latestAt).getTime() - new Date(a.latestAt).getTime(),
  )
})

function syncNewLogGroups() {
  const nextKnown = new Set(knownLogGroupKeys.value)
  const nextActive = new Set(activeLogGroups.value)
  for (const group of groupedLogs.value) {
    if (nextKnown.has(group.key)) continue
    nextKnown.add(group.key)
    nextActive.add(group.key)
  }
  knownLogGroupKeys.value = nextKnown
  activeLogGroups.value = [...nextActive].filter((key) =>
    groupedLogs.value.some((group) => group.key === key),
  )
}

async function load() {
  task.value = await getAnalysisTask(taskId)
  const flow = await getTaskNodes(taskId)
  nodes.value = flow.nodes
  edges.value = flow.edges
  logs.value = await getTaskLogs(taskId)
  metrics.value = await getTaskMetrics(taskId)
  syncNewLogGroups()
}

async function runControl(action: 'pause' | 'resume' | 'cancel' | 'retry') {
  if (controlLoading.value) {
    return
  }
  if (action === 'cancel') {
    await ElMessageBox.confirm('取消后当前任务会停止在最近的可检查节点，确认取消吗？', '取消任务', {
      type: 'warning',
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
    })
  }
  if (action === 'retry') {
    await ElMessageBox.confirm('重试会清理该任务已经生成的采集数据、证据、结论和报告，并从头重新执行。', '重试任务', {
      type: 'warning',
      confirmButtonText: '确认重试',
      cancelButtonText: '返回',
    })
  }
  controlLoading.value = action
  try {
    const handlers = {
      pause: pauseAnalysisTask,
      resume: resumeAnalysisTask,
      cancel: cancelAnalysisTask,
      retry: retryAnalysisTask,
    }
    task.value = await handlers[action](taskId)
    await load()
    ElMessage.success({ pause: '已提交暂停请求', resume: '任务已恢复', cancel: '已提交取消请求', retry: '任务已重新入队' }[action])
  } catch (error) {
    if (error === 'cancel') {
      return
    }
    const message = error instanceof Error ? error.message : '操作失败'
    ElMessage.error(message)
  } finally {
    controlLoading.value = null
  }
}

onMounted(async () => {
  await load()
  timer = window.setInterval(load, 2000)
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
        <el-button :disabled="!canPause" :loading="controlLoading === 'pause'" @click="runControl('pause')">
          暂停
        </el-button>
        <el-button :disabled="!canResume" :loading="controlLoading === 'resume'" @click="runControl('resume')">
          恢复
        </el-button>
        <el-button :disabled="!canRetry" :loading="controlLoading === 'retry'" @click="runControl('retry')">
          重试
        </el-button>
        <el-button :disabled="!canCancel" :loading="controlLoading === 'cancel'" type="danger" plain @click="runControl('cancel')">
          取消
        </el-button>
        <RouterLink :to="`/tasks/${taskId}/evidence`">
          <el-button>证据链</el-button>
        </RouterLink>
        <RouterLink :to="`/tasks/${taskId}/timing`">
          <el-button>阶段耗时</el-button>
        </RouterLink>
        <RouterLink :to="`/tasks/${taskId}/report`">
          <el-button type="primary">报告</el-button>
        </RouterLink>
      </div>
    </section>

    <section class="status-panel">
      <div class="status-main">
        <el-tag :type="statusType" effect="dark">{{ task?.status || 'loading' }}</el-tag>
        <span v-if="task?.status === 'queued'">任务已入队，等待 Celery Worker 接收。请确认 Worker 已启动并监听 competitor_agent_analysis 队列</span>
        <span v-else-if="task?.status === 'pause_requested'">暂停请求已提交，当前 Agent 到达检查点后会暂停</span>
        <span v-else-if="task?.status === 'paused'">任务已暂停，可点击恢复继续执行</span>
        <span v-else-if="task?.status === 'cancel_requested'">取消请求已提交，当前 Agent 到达检查点后会结束</span>
        <span v-else-if="task?.status === 'canceled'">任务已取消</span>
        <span v-else-if="currentNode">正在执行：{{ currentNode.node_name }}</span>
        <span v-else-if="task?.status === 'success'">分析完成</span>
        <span v-else-if="task?.status === 'failed'">任务失败：{{ task?.error_message }}</span>
        <span v-else>正在同步任务状态</span>
      </div>
      <el-progress :percentage="progress" :status="['failed', 'canceled'].includes(task?.status || '') ? 'exception' : task?.status === 'success' ? 'success' : undefined" />
    </section>

    <section class="node-grid">
      <div
        v-for="key in orderedNodeKeys"
        :key="key"
        class="node-card"
        :class="nodes.find((node) => node.node_key === key)?.status || 'pending'"
      >
        <strong>{{ nodes.find((node) => node.node_key === key)?.node_name || key }}</strong>
        <span>{{ nodes.find((node) => node.node_key === key)?.status || 'pending' }}</span>
      </div>
    </section>

    <DagFlow :nodes="nodes" :edges="edges" />

    <TaskMetricsPanel :metrics="metrics" />

    <section class="section">
      <h2>Agent 日志</h2>
      <el-collapse v-model="activeLogGroups" class="log-collapse">
        <el-collapse-item v-for="group in groupedLogs" :key="group.key" :name="group.key">
          <template #title>
            <div class="log-group-title">
              <strong>{{ group.nodeName }}</strong>
              <el-tag size="small" effect="plain">{{ group.nodeStatus }}</el-tag>
              <span>{{ group.logs.length }} 条动态</span>
              <time>{{ group.latestAt }}</time>
            </div>
          </template>
          <el-timeline class="log-timeline">
            <el-timeline-item
              v-for="log in group.logs"
              :key="log.id"
              :timestamp="log.created_at"
              :type="log.log_type === 'error' ? 'danger' : log.log_type === 'warning' ? 'warning' : 'primary'"
            >
              {{ log.message }}
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>
      </el-collapse>
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
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.status-panel {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: #fff;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.node-card {
  display: grid;
  gap: 6px;
  min-height: 66px;
  padding: 12px;
  border: 1px solid var(--el-border-color);
  border-left: 4px solid #909399;
  border-radius: 8px;
  background: #fff;
}

.node-card strong {
  font-size: 13px;
}

.node-card span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.node-card.running {
  border-left-color: #409eff;
}

.node-card.success {
  border-left-color: #67c23a;
}

.node-card.failed {
  border-left-color: #f56c6c;
}

.node-card.canceled,
.node-card.cancel_requested {
  border-left-color: #f56c6c;
}

.node-card.paused,
.node-card.pause_requested {
  border-left-color: #e6a23c;
}

.log-collapse {
  border-top: 1px solid var(--el-border-color);
}

.log-group-title {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto auto minmax(170px, auto);
  align-items: center;
  width: 100%;
  gap: 10px;
  padding-right: 12px;
}

.log-group-title strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-group-title span,
.log-group-title time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.log-timeline {
  padding: 4px 4px 0;
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

@media (max-width: 760px) {
  .log-group-title {
    grid-template-columns: minmax(120px, 1fr) auto;
  }

  .log-group-title time {
    grid-column: 1 / -1;
  }
}
</style>
