<script setup lang="ts">
import { computed } from 'vue'
import type { TaskMetrics } from '@/types/metrics'

const props = defineProps<{
  metrics: TaskMetrics | null
}>()

function percent(value: number) {
  return Math.round(value * 100)
}

function seconds(ms?: number | null) {
  if (!ms) return '-'
  return `${(ms / 1000).toFixed(1)} s`
}

const metricCards = computed(() => {
  const metrics = props.metrics
  if (!metrics) return []
  return [
    { label: '资料页数', value: metrics.source_document_count },
    { label: '证据片段', value: metrics.evidence_chunk_count },
    { label: '分析结论', value: metrics.claim_count },
    { label: '竞品画像', value: metrics.profile_count },
    { label: '对比表', value: metrics.matrix_count },
    { label: '向量失败', value: metrics.embedding_failed_count },
    { label: '检索降级', value: metrics.rag_fallback_count },
  ]
})
</script>

<template>
  <section class="metrics-panel">
    <header>
      <h2>运行指标</h2>
      <span v-if="metrics">总耗时 {{ seconds(metrics.total_duration_ms) }}</span>
    </header>
    <el-empty v-if="!metrics" description="暂无指标" />
    <template v-else>
      <div class="metric-grid">
        <div v-for="card in metricCards" :key="card.label" class="metric-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
        </div>
      </div>
      <div class="progress-grid">
        <div>
          <div class="progress-title">
            <span>证据覆盖率</span>
            <strong>{{ percent(metrics.evidence_coverage) }}%</strong>
          </div>
          <el-progress :percentage="percent(metrics.evidence_coverage)" />
        </div>
        <div>
          <div class="progress-title">
            <span>证据使用率</span>
            <strong>{{ percent(metrics.evidence_usage_rate) }}%</strong>
          </div>
          <el-progress :percentage="percent(metrics.evidence_usage_rate)" />
        </div>
      </div>
      <div class="metrics-columns">
        <div>
          <h3>证据来源分布</h3>
          <el-table :data="Object.entries(metrics.source_diversity).map(([type, count]) => ({ type, count }))" size="small">
            <el-table-column prop="type" label="来源" />
            <el-table-column prop="count" label="数量" width="90" />
          </el-table>
        </div>
        <div>
          <h3>节点耗时</h3>
          <el-table :data="metrics.node_durations" size="small">
            <el-table-column prop="node_name" label="节点" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="耗时" width="100">
              <template #default="{ row }">{{ seconds(row.duration_ms) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.metrics-panel {
  display: grid;
  gap: 16px;
  padding: 22px 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

header,
.progress-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.metric-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--ca-divider-soft);
  border-radius: 14px;
  background: var(--ca-pearl);
}

.metric-card span,
header span {
  color: var(--el-text-color-secondary);
}

.metric-card strong {
  color: var(--ca-ink);
  font-size: 28px;
  font-weight: 600;
  line-height: 1.1;
}

.progress-grid,
.metrics-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

h2,
h3 {
  margin: 0;
}

h2 {
  font-size: 24px;
  font-weight: 600;
}

h3 {
  margin-bottom: 8px;
  font-size: 17px;
  font-weight: 600;
}

@media (max-width: 900px) {
  .progress-grid,
  .metrics-columns {
    grid-template-columns: 1fr;
  }
}
</style>
