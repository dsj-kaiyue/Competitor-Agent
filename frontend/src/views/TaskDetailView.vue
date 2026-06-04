<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DagFlow from '@/components/DagFlow.vue'
import QaResultPanel from '@/components/QaResultPanel.vue'
import TaskMetricsPanel from '@/components/TaskMetricsPanel.vue'
import TaskTimingPanel from '@/components/TaskTimingPanel.vue'
import {
  cancelAnalysisTask,
  getAnalysisTask,
  getTaskMetrics,
  getTaskLogs,
  getTaskNodes,
  getTaskQaHistory,
  pauseAnalysisTask,
  resumeAnalysisTask,
  retryAnalysisTask,
} from '@/api/analysisTaskApi'
import type { AgentLog, AgentNode, DagEdge } from '@/types/agentNode'
import type { AnalysisTask } from '@/types/analysisTask'
import type { TaskMetrics } from '@/types/metrics'
import type { QAResult } from '@/types/qa'

const route = useRoute()
const taskId = Number(route.params.id)
const task = ref<AnalysisTask | null>(null)
const nodes = ref<AgentNode[]>([])
const edges = ref<DagEdge[]>([])
const logs = ref<AgentLog[]>([])
const metrics = ref<TaskMetrics | null>(null)
const qaHistory = ref<QAResult[]>([])
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

const baseNodeOrder = ['planner', 'dimension_planner', 'collector', 'evidence_extractor']
const tailNodeOrder = ['report_writer', 'qa', 'report_finalizer']
const orderedNodes = computed(() => {
  const byKey = new Map(nodes.value.map((node) => [node.node_key, node]))
  const head = baseNodeOrder.map((key) => byKey.get(key)).filter((node): node is AgentNode => Boolean(node))
  const dimensionNodes = nodes.value.filter((node) => node.node_type === 'dimension_analyst')
  const tail = tailNodeOrder.map((key) => byKey.get(key)).filter((node): node is AgentNode => Boolean(node))
  const seen = new Set([...head, ...dimensionNodes, ...tail].map((node) => node.node_key))
  const rest = nodes.value.filter((node) => !seen.has(node.node_key) && node.node_type !== 'virtual_worker')
  return [...head, ...dimensionNodes, ...tail, ...rest]
})

const currentNode = computed(() => nodes.value.find((node) => node.status === 'running'))
const completedCount = computed(() => nodes.value.filter((node) => node.status === 'success').length)
const latestQa = computed(() => qaHistory.value[qaHistory.value.length - 1] || null)
const dimensionQaRoundRows = computed(() =>
  qaHistory.value.flatMap((qa) => {
    const scores = qa.dimension_scores?.length ? qa.dimension_scores : qa.current_dimension_scores || []
    return scores.map((score) => ({
      qa_id: qa.id,
      created_at: qa.created_at,
      revision_round: qa.revision_round ?? score.revision_round ?? 0,
      qa_scope_label: qa.qa_scope_label || score.qa_scope_label || qa.qa_scope || '-',
      dimension_label: score.dimension_label || score.dimension_key || score.target_node,
      score: score.score ?? '-',
      passed: Boolean(score.passed),
    }))
  }),
)
const canPause = computed(() =>
  ['queued', 'running', 'planned', 'planning_dimensions', 'collecting', 'extracting', 'analyzing', 'writing', 'qa_checking', 'finalizing'].includes(
    task.value?.status || '',
  ),
)
const canResume = computed(() => ['paused', 'pause_requested'].includes(task.value?.status || ''))
const canCancel = computed(() =>
  ['queued', 'running', 'planned', 'planning_dimensions', 'collecting', 'extracting', 'analyzing', 'writing', 'qa_checking', 'finalizing', 'pause_requested', 'paused'].includes(
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

async function load() {
  task.value = await getAnalysisTask(taskId)
  const flow = await getTaskNodes(taskId)
  nodes.value = flow.nodes
  edges.value = flow.edges
  logs.value = await getTaskLogs(taskId)
  metrics.value = await getTaskMetrics(taskId)
  qaHistory.value = await getTaskQaHistory(taskId)
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
        v-for="node in orderedNodes"
        :key="node.node_key"
        class="node-card"
        :class="[node.status || 'pending', { 'revision-highlight': node.revision_highlight }]"
      >
        <strong>{{ node.node_name }}</strong>
        <span>{{ node.status || 'pending' }}</span>
      </div>
    </section>

    <DagFlow :nodes="nodes" :edges="edges" />

    <TaskMetricsPanel :metrics="metrics" />

    <section class="section">
      <h2>QA 结果</h2>
      <QaResultPanel :qa="latestQa" />
      <div class="qa-history">
        <h3>每轮每维 QA 得分</h3>
        <el-empty v-if="!dimensionQaRoundRows.length" description="暂无每维 QA 分数" />
        <el-table v-else :data="dimensionQaRoundRows" border>
          <el-table-column label="轮次" width="100">
            <template #default="{ row }">第 {{ row.revision_round }} 轮</template>
          </el-table-column>
          <el-table-column label="时间" min-width="180">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="dimension_label" label="维度" min-width="180" />
          <el-table-column label="分数" width="100">
            <template #default="{ row }">{{ row.score }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.passed ? 'success' : 'warning'" size="small">
                {{ row.passed ? '通过' : '未通过' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="qa_scope_label" label="检查范围" width="150" />
        </el-table>
      </div>
    </section>

    <TaskTimingPanel :logs="logs" />

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

.node-card.revision-highlight {
  border-color: #e6a23c;
  border-left-color: #e6a23c;
  background: #fff8e8;
  box-shadow: 0 0 0 3px rgba(230, 162, 60, 0.14);
}

.qa-history {
  display: grid;
  gap: 10px;
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
h3,
p {
  margin: 0;
}

h1 {
  font-size: 22px;
}

h2 {
  font-size: 18px;
}

h3 {
  font-size: 15px;
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
