<script setup lang="ts">
import { computed } from 'vue'
import type { QAResult } from '@/types/qa'

const props = defineProps<{ qa: QAResult | null }>()

const severityType: Record<string, 'danger' | 'warning' | 'info'> = {
  high: 'danger',
  medium: 'warning',
  low: 'info',
}

const actionLabels: Record<string, string> = {
  end: '无需返工',
  recollect: '重新收集资料',
  reanalyze: '重新分析',
  rewrite: '重写报告',
  ignore: '忽略',
}

const severityLabels: Record<string, string> = {
  high: '高风险',
  medium: '中等风险',
  low: '低风险',
}

const issueTypeLabels: Record<string, string> = {
  missing_evidence: '缺少证据',
  weak_evidence: '证据较弱',
  unsupported_claim: '结论缺少支撑',
  contradiction: '结论矛盾',
  outdated_source: '来源过期',
  schema_incomplete: '结构不完整',
  logic_gap: '逻辑缺口',
  writing_issue: '写作问题',
}

const actionLabel = computed(() => {
  const action = props.qa?.next_action || 'end'
  return props.qa?.next_action_label || actionLabels[action] || action
})

const targetLabels = computed(() => {
  if (props.qa?.target_node_labels?.length) return props.qa.target_node_labels
  return props.qa?.target_nodes || []
})

const qaScopeLabel = computed(() => props.qa?.qa_scope_label || (props.qa?.qa_scope === 'partial_revision' ? '本轮返工维度' : '完整报告'))

const dimensionScores = computed(() => props.qa?.dimension_scores || [])

const revisionReasonItems = computed(() => {
  const reason = props.qa?.revision_reason?.trim()
  if (!reason) return []
  return reason
    .split(/\s*(?:\r?\n|；|;)\s*/g)
    .map((item) => item.trim())
    .filter(Boolean)
})

function issueSeverityLabel(severity?: string) {
  return severity ? severityLabels[severity] || severity : '-'
}

function issueTypeLabel(type?: string) {
  return type ? issueTypeLabels[type] || type : '-'
}

function issueActionLabel(action?: string) {
  return action ? actionLabels[action] || action : '-'
}

function displayRevisionRound(value?: number | null) {
  return Math.max(1, Number(value ?? 0) + 1)
}
</script>

<template>
  <el-empty v-if="!qa" description="暂无 QA 结果" />
  <div v-else class="qa-panel">
    <div class="qa-summary" :class="{ passed: qa.passed }">
      <div class="status-mark">{{ qa.passed ? '✓' : '!' }}</div>
      <div>
        <h3>{{ qa.passed ? 'QA 通过' : 'QA 未通过，需要处理' }}</h3>
        <p>评分 {{ qa.score ?? '-' }} · {{ qaScopeLabel }} · 第 {{ displayRevisionRound(qa.revision_round) }} 轮返工 · {{ actionLabel }}</p>
      </div>
    </div>

    <div class="qa-overview">
      <div class="overview-item">
        <span>QA 结论</span>
        <strong>{{ qa.passed ? '通过' : '未通过' }}</strong>
      </div>
      <div class="overview-item">
        <span>QA 评分</span>
        <strong>{{ qa.score ?? '-' }}</strong>
      </div>
      <div class="overview-item">
        <span>检查范围</span>
        <strong>{{ qaScopeLabel }}</strong>
      </div>
      <div class="overview-item">
        <span>返工轮次</span>
        <strong>第 {{ displayRevisionRound(qa.revision_round) }} 轮</strong>
      </div>
      <div class="overview-item">
        <span>建议处理</span>
        <strong>{{ actionLabel }}</strong>
      </div>
    </div>

    <div v-if="targetLabels.length" class="qa-section">
      <div class="section-title">涉及节点/维度</div>
      <div class="target-list">
        <el-tag v-for="node in targetLabels" :key="node" type="warning" effect="plain">
          {{ node }}
        </el-tag>
      </div>
    </div>

    <div v-if="dimensionScores.length" class="qa-section">
      <div class="section-title">每维 QA 分数</div>
      <el-table :data="dimensionScores" border>
        <el-table-column label="维度">
          <template #default="{ row }">{{ row.dimension_label || row.dimension_key || row.target_node }}</template>
        </el-table-column>
        <el-table-column label="分数" width="100">
          <template #default="{ row }">{{ row.score ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.passed ? 'success' : 'warning'" size="small">
              {{ row.passed ? '通过' : '未通过' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="检查范围" width="150">
          <template #default="{ row }">{{ row.qa_scope_label || row.qa_scope || '-' }}</template>
        </el-table-column>
        <el-table-column label="轮次" width="100">
          <template #default="{ row }">第 {{ displayRevisionRound(row.revision_round) }} 轮</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="revisionReasonItems.length && !qa.issues.length" class="qa-section">
      <div class="section-title">返工原因</div>
      <ol class="reason-list">
        <li v-for="(reason, index) in revisionReasonItems" :key="`${index}-${reason}`">
          {{ reason }}
        </li>
      </ol>
    </div>

    <el-table v-if="qa.issues.length" :data="qa.issues" border>
      <el-table-column label="级别" width="110">
        <template #default="{ row }">
          <el-tag :type="severityType[row.severity] || 'info'" size="small">
            {{ row.severity_label || issueSeverityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">{{ row.type_label || issueTypeLabel(row.type) }}</template>
      </el-table-column>
      <el-table-column prop="message" label="问题" />
      <el-table-column label="维度/节点" width="180">
        <template #default="{ row }">{{ row.related_dimension || row.target_node_label || '-' }}</template>
      </el-table-column>
      <el-table-column label="建议" width="140">
        <template #default="{ row }">{{ row.suggested_action_label || issueActionLabel(row.suggested_action) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.qa-panel {
  display: grid;
  gap: 16px;
}

.qa-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border: 1px solid #f3d19e;
  border-radius: 8px;
  background: #fdf6ec;
}

.qa-summary.passed {
  border-color: #b3e19d;
  background: #f0f9eb;
}

.status-mark {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  place-items: center;
  border-radius: 50%;
  background: #e6a23c;
  color: #fff;
  font-size: 24px;
  font-weight: 700;
}

.qa-summary.passed .status-mark {
  background: #67c23a;
}

.qa-summary h3 {
  margin: 0 0 4px;
  font-size: 18px;
}

.qa-summary p {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.qa-overview {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.overview-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.overview-item span,
.section-title {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.overview-item strong {
  color: var(--el-text-color-primary);
  font-size: 15px;
}

.qa-section {
  display: grid;
  gap: 8px;
}

.target-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.reason-list {
  margin: 0;
  padding-left: 22px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.reason-list li + li {
  margin-top: 6px;
}

@media (max-width: 1080px) {
  .qa-overview {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .qa-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
