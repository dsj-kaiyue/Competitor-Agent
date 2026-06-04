<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DagFlow from '@/components/DagFlow.vue'
import QaResultPanel from '@/components/QaResultPanel.vue'
import TaskMetricsPanel from '@/components/TaskMetricsPanel.vue'
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
const activeQaRounds = ref<string[]>([])
const activeLogRounds = ref<string[]>([])
const activeLogAgentGroups = ref<string[]>([])
const controlLoading = ref<string | null>(null)
const qaRoundsInitialized = ref(false)
const logGroupsInitialized = ref(false)
let timer: number | undefined

interface AgentLogGroup {
  key: string
  nodeName: string
  nodeStatus: string
  latestAt: string
  logs: AgentLog[]
}

interface AgentLogRoundGroup {
  key: string
  revision_round: number
  display_round: number
  latestAt: string
  logCount: number
  agentGroups: AgentLogGroup[]
}

interface DimensionQaRoundRow {
  row_key: string
  qa_id: number
  created_at: string
  revision_round: number
  display_round: number
  qa_scope_label: string
  dimension_label: string
  dimension_keys: string[]
  score: number | string
  passed: boolean
  suggestion: string
}

interface DimensionQaRoundGroup {
  key: string
  revision_round: number
  display_round: number
  created_at: string
  qa_scope_label: string
  passed_count: number
  total_count: number
  rows: DimensionQaRoundRow[]
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
const actionLabels: Record<string, string> = {
  recollect: '重新收集资料',
  reanalyze: '重新分析',
  rewrite: '重写报告',
  ignore: '忽略',
  end: '无需返工',
}

function displayRevisionRound(value?: number | null) {
  return Math.max(1, Number(value ?? 0) + 1)
}

function dimensionKeys(score: {
  dimension_label?: string | null
  dimension_key?: string | null
  target_node?: string | null
}) {
  return [score.dimension_label, score.dimension_key, score.target_node].filter((value): value is string =>
    Boolean(value),
  )
}

function issueMatchesDimension(issue: { related_dimension?: string | null; target_node?: string | null; target_node_label?: string | null }, keys: string[]) {
  const issueKeys = [issue.related_dimension, issue.target_node, issue.target_node_label].filter((value): value is string =>
    Boolean(value),
  )
  return issueKeys.some((issueKey) => keys.includes(issueKey))
}

function rowSuggestion(score: { passed?: boolean; issues?: { suggested_action?: string; suggested_action_label?: string }[] }, qa: QAResult, keys: string[]) {
  if (score.passed) return '-'
  const scoreIssues = score.issues || []
  const matchedIssues = [
    ...scoreIssues,
    ...qa.issues.filter((issue) => issueMatchesDimension(issue, keys)),
  ]
  const labels = [...new Set(
    matchedIssues
      .map((issue) => issue.suggested_action_label || (issue.suggested_action ? actionLabels[issue.suggested_action] || issue.suggested_action : ''))
      .filter(Boolean),
  )]
  if (labels.length) return labels.join(' / ')
  return qa.next_action_label || (qa.next_action ? actionLabels[qa.next_action] || qa.next_action : '待处理')
}

const dimensionQaRoundRows = computed<DimensionQaRoundRow[]>(() =>
  qaHistory.value.flatMap((qa) => {
    const scores = qa.current_dimension_scores?.length ? qa.current_dimension_scores : qa.dimension_scores || []
    const revisionRound = Number(qa.revision_round ?? 0)
    return scores.map((score, index) => {
      const keys = dimensionKeys(score)
      return {
      row_key: `${qa.id}-${score.target_node || score.dimension_key || score.dimension_label || index}`,
      qa_id: qa.id,
      created_at: qa.created_at,
      revision_round: revisionRound,
      display_round: displayRevisionRound(revisionRound),
      qa_scope_label: qa.qa_scope_label || score.qa_scope_label || qa.qa_scope || '-',
      dimension_label: score.dimension_label || score.dimension_key || score.target_node,
      dimension_keys: keys,
      score: score.score ?? '-',
      passed: Boolean(score.passed),
      suggestion: rowSuggestion(score, qa, keys),
      }
    })
  }),
)
const dimensionQaRoundGroups = computed<DimensionQaRoundGroup[]>(() => {
  const groups = new Map<string, DimensionQaRoundGroup>()
  for (const row of dimensionQaRoundRows.value) {
    const groupKey = String(row.revision_round)
    const group = groups.get(groupKey)
    if (group) {
      group.rows.push(row)
      group.total_count += 1
      group.passed_count += row.passed ? 1 : 0
      if (new Date(row.created_at).getTime() > new Date(group.created_at).getTime()) {
        group.created_at = row.created_at
      }
      continue
    }
    groups.set(groupKey, {
      key: groupKey,
      revision_round: row.revision_round,
      display_round: row.display_round,
      created_at: row.created_at,
      qa_scope_label: row.qa_scope_label,
      passed_count: row.passed ? 1 : 0,
      total_count: 1,
      rows: [row],
    })
  }
  return [...groups.values()].sort((a, b) => {
    if (b.revision_round !== a.revision_round) return b.revision_round - a.revision_round
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})
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
const qaBoundaries = computed(() =>
  [...qaHistory.value]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .map((qa) => ({
      createdAt: new Date(qa.created_at).getTime(),
      revisionRound: Number(qa.revision_round ?? 0),
    })),
)
const revisionMarkers = computed(() =>
  logs.value
    .map((log) => ({
      createdAt: new Date(log.created_at).getTime(),
      revisionRound: Number(log.payload?.revision_round),
    }))
    .filter((marker) => Number.isFinite(marker.revisionRound) && marker.revisionRound > 0)
    .sort((a, b) => a.createdAt - b.createdAt),
)

function logRevisionRound(log: AgentLog) {
  const payloadRound = Number(log.payload?.revision_round)
  if (Number.isFinite(payloadRound) && payloadRound >= 0) {
    return payloadRound
  }
  const logTime = new Date(log.created_at).getTime()
  const latestMarker = [...revisionMarkers.value].reverse().find((marker) => marker.createdAt <= logTime)
  if (latestMarker) {
    return latestMarker.revisionRound
  }
  for (const boundary of qaBoundaries.value) {
    if (logTime <= boundary.createdAt) {
      return boundary.revisionRound
    }
  }
  const latest = qaBoundaries.value[qaBoundaries.value.length - 1]
  return latest ? latest.revisionRound : 0
}

const groupedLogRounds = computed<AgentLogRoundGroup[]>(() => {
  const roundGroups = new Map<number, Map<string, AgentLogGroup>>()
  const latestByRound = new Map<number, string>()
  for (const log of sortedLogs.value) {
    const node = log.node_id ? nodeById.value.get(log.node_id) : undefined
    const revisionRound = logRevisionRound(log)
    const agentGroups = roundGroups.get(revisionRound) || new Map<string, AgentLogGroup>()
    roundGroups.set(revisionRound, agentGroups)
    latestByRound.set(revisionRound, latestByRound.get(revisionRound) || log.created_at)
    const key = `${revisionRound}:${node ? String(node.id) : 'system'}`
    const group = agentGroups.get(key)
    if (group) {
      group.logs.push(log)
      continue
    }
    agentGroups.set(key, {
      key,
      nodeName: node?.node_name || '系统日志',
      nodeStatus: node?.status || 'info',
      latestAt: log.created_at,
      logs: [log],
    })
  }
  const result: AgentLogRoundGroup[] = []
  for (const [revisionRound, agentGroups] of roundGroups.entries()) {
    const agentGroupList = [...agentGroups.values()].sort(
      (a, b) => new Date(b.latestAt).getTime() - new Date(a.latestAt).getTime(),
    )
    result.push({
      key: String(revisionRound),
      revision_round: revisionRound,
      display_round: displayRevisionRound(revisionRound),
      latestAt: latestByRound.get(revisionRound) || agentGroupList[0]?.latestAt || '',
      logCount: agentGroupList.reduce((sum, group) => sum + group.logs.length, 0),
      agentGroups: agentGroupList,
    })
  }
  return result.sort((a, b) =>
    b.revision_round !== a.revision_round
      ? b.revision_round - a.revision_round
      : new Date(b.latestAt).getTime() - new Date(a.latestAt).getTime(),
  )
})

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

function resetDetailStateForRetry() {
  logs.value = []
  qaHistory.value = []
  activeQaRounds.value = []
  activeLogRounds.value = []
  activeLogAgentGroups.value = []
  qaRoundsInitialized.value = false
  logGroupsInitialized.value = false
}

watch(
  dimensionQaRoundGroups,
  (groups) => {
    if (!groups.length) {
      activeQaRounds.value = []
      return
    }
    if (!qaRoundsInitialized.value) {
      activeQaRounds.value = [groups[0]?.key || '']
      qaRoundsInitialized.value = true
      return
    }
    const existing = new Set(activeQaRounds.value)
    activeQaRounds.value = [...existing].filter((key) => groups.some((group) => group.key === key))
  },
  { immediate: true },
)

watch(
  groupedLogRounds,
  (rounds) => {
    if (!rounds.length) {
      activeLogRounds.value = []
      activeLogAgentGroups.value = []
      return
    }
    if (!logGroupsInitialized.value) {
      const latestRound = rounds[0]
      activeLogRounds.value = latestRound ? [latestRound.key] : []
      activeLogAgentGroups.value = latestRound?.agentGroups.map((group) => group.key) || []
      logGroupsInitialized.value = true
      return
    }
    const roundKeys = new Set(rounds.map((round) => round.key))
    const agentKeys = new Set(rounds.flatMap((round) => round.agentGroups.map((group) => group.key)))
    activeLogRounds.value = activeLogRounds.value.filter((key) => roundKeys.has(key))
    activeLogAgentGroups.value = activeLogAgentGroups.value.filter((key) => agentKeys.has(key))
  },
  { immediate: true },
)

async function load() {
  task.value = await getAnalysisTask(taskId)
  const flow = await getTaskNodes(taskId)
  nodes.value = flow.nodes
  edges.value = flow.edges
  logs.value = await getTaskLogs(taskId)
  metrics.value = await getTaskMetrics(taskId)
  qaHistory.value = await getTaskQaHistory(taskId)
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
    if (action === 'retry') {
      resetDetailStateForRetry()
    }
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

    <section class="section">
      <h2>QA 结果</h2>
      <QaResultPanel :qa="latestQa" />
      <div class="qa-history">
        <h3>每轮每维 QA 得分</h3>
        <el-empty v-if="!dimensionQaRoundGroups.length" description="暂无每维 QA 分数" />
        <el-collapse v-else v-model="activeQaRounds" class="qa-round-collapse">
          <el-collapse-item v-for="group in dimensionQaRoundGroups" :key="group.key" :name="group.key">
            <template #title>
              <div class="qa-round-title">
                <strong>第 {{ group.display_round }} 轮</strong>
                <el-tag :type="group.passed_count === group.total_count ? 'success' : 'warning'" size="small">
                  {{ group.passed_count }}/{{ group.total_count }} 通过
                </el-tag>
                <span>{{ group.qa_scope_label }}</span>
                <time>{{ formatDateTime(group.created_at) }}</time>
              </div>
            </template>
            <el-table :data="group.rows" border>
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
              <el-table-column label="返工建议" min-width="160">
                <template #default="{ row }">{{ row.suggestion }}</template>
              </el-table-column>
              <el-table-column prop="qa_scope_label" label="检查范围" width="150" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>
    </section>

    <TaskMetricsPanel :metrics="metrics" />

    <section class="section">
      <h2>Agent 日志</h2>
      <el-empty v-if="!groupedLogRounds.length" description="暂无 Agent 日志" />
      <el-collapse v-else v-model="activeLogRounds" class="log-collapse">
        <el-collapse-item v-for="round in groupedLogRounds" :key="round.key" :name="round.key">
          <template #title>
            <div class="log-round-title">
              <strong>第 {{ round.display_round }} 轮</strong>
              <el-tag size="small" effect="plain">{{ round.agentGroups.length }} 个 Agent</el-tag>
              <span>{{ round.logCount }} 条动态</span>
              <time>{{ formatDateTime(round.latestAt) }}</time>
            </div>
          </template>
          <el-collapse v-model="activeLogAgentGroups" class="agent-log-collapse">
            <el-collapse-item v-for="group in round.agentGroups" :key="group.key" :name="group.key">
              <template #title>
                <div class="log-group-title">
                  <strong>{{ group.nodeName }}</strong>
                  <el-tag size="small" effect="plain">{{ group.nodeStatus }}</el-tag>
                  <span>{{ group.logs.length }} 条动态</span>
                  <time>{{ formatDateTime(group.latestAt) }}</time>
                </div>
              </template>
              <el-timeline class="log-timeline">
                <el-timeline-item
                  v-for="log in group.logs"
                  :key="log.id"
                  :timestamp="formatDateTime(log.created_at)"
                  :type="log.log_type === 'error' ? 'danger' : log.log_type === 'warning' ? 'warning' : 'primary'"
                >
                  {{ log.message }}
                </el-timeline-item>
              </el-timeline>
            </el-collapse-item>
          </el-collapse>
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

.qa-round-collapse {
  border-top: 1px solid var(--el-border-color);
}

.qa-round-title {
  display: grid;
  grid-template-columns: minmax(100px, auto) auto minmax(120px, 1fr) minmax(170px, auto);
  align-items: center;
  width: 100%;
  gap: 10px;
  padding-right: 12px;
}

.qa-round-title span,
.qa-round-title time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.log-collapse {
  border-top: 1px solid var(--el-border-color);
}

.agent-log-collapse {
  border-top: 0;
}

.log-round-title,
.log-group-title {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto auto minmax(170px, auto);
  align-items: center;
  width: 100%;
  gap: 10px;
  padding-right: 12px;
}

.log-round-title strong,
.log-group-title strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-round-title span,
.log-round-title time,
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
  .log-round-title,
  .log-group-title {
    grid-template-columns: minmax(120px, 1fr) auto;
  }

  .qa-round-title {
    grid-template-columns: minmax(100px, 1fr) auto;
  }

  .log-round-title time,
  .log-group-title time,
  .qa-round-title time,
  .qa-round-title span {
    grid-column: 1 / -1;
  }
}
</style>
