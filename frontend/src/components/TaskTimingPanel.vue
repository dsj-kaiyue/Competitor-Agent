<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentLog } from '@/types/agentNode'

const props = defineProps<{
  logs: AgentLog[]
}>()

const selectedMetricId = ref<number | null>(null)

interface TimingMetric {
  id: number
  message: string
  created_at: string
  stage: string
  document_count: number
  chunk_count: number
  batch_count: number
  batch_size: number
  max_workers: number
  chunking_ms: number
  mysql_create_ms: number
  embedding_wall_ms: number
  embedding_worker_ms: number
  milvus_batch_insert_ms: number
  mysql_update_ms: number
  total_ms: number
  failed: number
  attempt_number?: number
}

function numberValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return typeof value === 'number' ? value : Number(value || 0)
}

function metricFromLog(log: AgentLog): TimingMetric | null {
  if (log.log_type !== 'metric' || !log.payload) {
    return null
  }
  const payload = log.payload
  return {
    id: log.id,
    message: log.message,
    created_at: log.created_at,
    stage: String(payload.stage || 'unknown'),
    document_count: numberValue(payload, 'document_count'),
    chunk_count: numberValue(payload, 'chunk_count'),
    batch_count: numberValue(payload, 'batch_count'),
    batch_size: numberValue(payload, 'batch_size'),
    max_workers: numberValue(payload, 'max_workers'),
    chunking_ms: numberValue(payload, 'chunking_ms'),
    mysql_create_ms: numberValue(payload, 'mysql_create_ms'),
    embedding_wall_ms: numberValue(payload, 'embedding_wall_ms'),
    embedding_worker_ms: numberValue(payload, 'embedding_worker_ms'),
    milvus_batch_insert_ms: numberValue(payload, 'milvus_batch_insert_ms'),
    mysql_update_ms: numberValue(payload, 'mysql_update_ms'),
    total_ms: numberValue(payload, 'total_ms'),
    failed: numberValue(payload, 'failed'),
  }
}

const metrics = computed(() =>
  props.logs
    .map(metricFromLog)
    .filter((metric): metric is TimingMetric => Boolean(metric))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
)

const completedAttempts = computed(() => {
  const completed = metrics.value
    .filter((metric) => metric.total_ms > 0)
    .sort((a, b) => parseBackendTime(a.created_at).getTime() - parseBackendTime(b.created_at).getTime())
    .map((metric, index) => ({ ...metric, attempt_number: index + 1 }))
  return completed.sort((a, b) => parseBackendTime(b.created_at).getTime() - parseBackendTime(a.created_at).getTime())
})

const selectedMetric = computed(() => {
  if (!completedAttempts.value.length) return null
  return completedAttempts.value.find((metric) => metric.id === selectedMetricId.value) || completedAttempts.value[0]
})

const maxDuration = computed(() => {
  const metric = selectedMetric.value
  if (!metric) return 1
  return Math.max(
    metric.chunking_ms,
    metric.mysql_create_ms,
    metric.embedding_wall_ms,
    metric.milvus_batch_insert_ms,
    metric.mysql_update_ms,
    1,
  )
})

const timingRows = computed(() => {
  const metric = selectedMetric.value
  if (!metric) return []
  return [
    { name: '文本切块', value: metric.chunking_ms },
    { name: 'MySQL 创建 Chunk', value: metric.mysql_create_ms },
    { name: '批量 Embedding', value: metric.embedding_wall_ms },
    { name: 'Milvus 批量写入', value: metric.milvus_batch_insert_ms },
    { name: 'MySQL 更新向量 ID', value: metric.mysql_update_ms },
  ]
})

function formatMs(value: number) {
  if (!value) return '-'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(2)} s`
}

function parseBackendTime(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(value)
  return new Date(hasTimezone ? value : value)
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
  }).format(parseBackendTime(value))
}

function barWidth(value: number) {
  return `${Math.max(4, Math.round((value / maxDuration.value) * 100))}%`
}
</script>

<template>
  <section class="timing-shell">
    <header>
      <div>
        <h2>阶段耗时</h2>
        <p>证据抽取性能指标</p>
      </div>
    </header>

    <el-empty v-if="!metrics.length" description="暂无阶段耗时日志" />

    <section v-if="completedAttempts.length" class="attempt-panel">
      <div>
        <h3>证据抽取轮次</h3>
        <p>QA 返工会产生多次证据抽取，默认展示最新一轮。</p>
      </div>
      <el-select v-model="selectedMetricId" placeholder="最新一轮" clearable class="attempt-select">
        <el-option
          v-for="metric in completedAttempts"
          :key="metric.id"
          :label="`第 ${metric.attempt_number} 次 · ${formatDateTime(metric.created_at)} · ${formatMs(metric.total_ms)}`"
          :value="metric.id"
        />
      </el-select>
    </section>

    <section v-if="selectedMetric" class="summary-grid">
      <div class="summary-item">
        <span>SourceDocument</span>
        <strong>{{ selectedMetric.document_count }}</strong>
      </div>
      <div class="summary-item">
        <span>Evidence Chunk</span>
        <strong>{{ selectedMetric.chunk_count }}</strong>
      </div>
      <div class="summary-item">
        <span>Embedding 批次</span>
        <strong>{{ selectedMetric.batch_count }} × {{ selectedMetric.batch_size }}</strong>
      </div>
      <div class="summary-item">
        <span>并发 Worker</span>
        <strong>{{ selectedMetric.max_workers }}</strong>
      </div>
      <div class="summary-item">
        <span>总耗时</span>
        <strong>{{ formatMs(selectedMetric.total_ms) }}</strong>
      </div>
      <div class="summary-item">
        <span>Embedding 失败</span>
        <strong>{{ selectedMetric.failed }}</strong>
      </div>
    </section>

    <section v-if="timingRows.length" class="timing-panel">
      <article v-for="row in timingRows" :key="row.name" class="timing-row">
        <div class="timing-label">
          <strong>{{ row.name }}</strong>
          <span>{{ formatMs(row.value) }}</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: barWidth(row.value) }" />
        </div>
      </article>
    </section>

    <section v-if="metrics.length" class="section">
      <h3>原始指标日志</h3>
      <el-table :data="metrics" border>
        <el-table-column label="时间" min-width="190">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="message" label="事件" min-width="260" />
        <el-table-column label="Chunk" width="90">
          <template #default="{ row }">{{ row.chunk_count || '-' }}</template>
        </el-table-column>
        <el-table-column label="批次" width="90">
          <template #default="{ row }">{{ row.batch_count || '-' }}</template>
        </el-table-column>
        <el-table-column label="Embedding" width="120">
          <template #default="{ row }">{{ formatMs(row.embedding_wall_ms) }}</template>
        </el-table-column>
        <el-table-column label="Milvus" width="120">
          <template #default="{ row }">{{ formatMs(row.milvus_batch_insert_ms) }}</template>
        </el-table-column>
        <el-table-column label="总耗时" width="120">
          <template #default="{ row }">{{ formatMs(row.total_ms) }}</template>
        </el-table-column>
        <el-table-column label="失败" width="90">
          <template #default="{ row }">{{ row.failed || 0 }}</template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>

<style scoped>
.timing-shell,
.section,
.timing-panel {
  display: grid;
  gap: 18px;
}

.timing-shell {
  padding: 22px 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

header,
.timing-label,
.attempt-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}

.summary-item,
.attempt-panel,
.timing-panel {
  padding: 16px;
  border: 1px solid var(--ca-divider-soft);
  border-radius: 14px;
  background: var(--ca-pearl);
}

.attempt-select {
  width: 360px;
  max-width: 100%;
}

.summary-item {
  display: grid;
  gap: 4px;
}

.summary-item span,
p,
.timing-label span {
  color: var(--el-text-color-secondary);
}

.summary-item strong {
  color: var(--ca-ink);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
}

.timing-row {
  display: grid;
  gap: 8px;
}

.bar-track {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--el-fill-color-light);
}

.bar-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--el-color-primary);
}

h2,
h3,
p {
  margin: 0;
}

h2 {
  font-size: 24px;
  font-weight: 600;
}

h3 {
  font-size: 17px;
  font-weight: 600;
}

@media (max-width: 760px) {
  header,
  .attempt-panel,
  .timing-label {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
