<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { QAIssue, QAResult } from '@/types/qa'
import type { ReportItem } from '@/types/report'

interface DimensionQaRoundRow {
  row_key: string
  created_at: string
  revision_round: number
  display_round: number
  qa_scope_label: string
  dimension_label: string
  dimension_keys?: string[]
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

const props = defineProps<{
  qa: QAResult | null
  report?: ReportItem | null
  dimensionQaRoundGroups?: DimensionQaRoundGroup[]
}>()

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

const latestDimensionRows = computed<DimensionQaRoundRow[]>(() => {
  const latestByDimension = new Map<string, DimensionQaRoundRow>()
  for (const group of props.dimensionQaRoundGroups || []) {
    for (const row of group.rows) {
      const dimensionKey = row.dimension_keys?.[0] || row.dimension_label
      if (!latestByDimension.has(dimensionKey)) {
        latestByDimension.set(dimensionKey, row)
      }
    }
  }
  if (latestByDimension.size) {
    return [...latestByDimension.values()].sort((a, b) => a.dimension_label.localeCompare(b.dimension_label, 'zh-Hans-CN'))
  }
  return (props.qa?.dimension_scores || []).map((score, index) => ({
    row_key: `latest-${score.target_node || score.dimension_key || score.dimension_label || index}`,
    created_at: props.qa?.created_at || '',
    revision_round: Number(score.revision_round ?? props.qa?.revision_round ?? 0),
    display_round: displayRevisionRound(Number(score.revision_round ?? props.qa?.revision_round ?? 0)),
    qa_scope_label: score.qa_scope_label || score.qa_scope || qaScopeLabel.value,
    dimension_label: score.dimension_label || score.dimension_key || score.target_node,
    dimension_keys: [score.target_node, score.dimension_key, score.dimension_label].filter((value): value is string => Boolean(value)),
    score: score.score ?? '-',
    passed: Boolean(score.passed),
    suggestion: score.issues?.[0]?.suggested_action_label || issueActionLabel(score.issues?.[0]?.suggested_action),
  }))
})
const qualitySummary = computed(() => props.report?.report_json?.quality_summary || null)
const finalizerQa = computed(() => props.report?.report_json?.finalizer_qa || null)
const finalizerIssues = computed(() => finalizerQa.value?.issues || [])
const activeIssueGroups = ref<string[]>([])
const issueGroupsInitializedForQa = ref<number | null>(null)
const activeHistoryRounds = ref<string[]>([])
const historyRoundsInitialized = ref(false)

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

function finalizerRound(value?: number | null) {
  return Math.max(1, Number(value ?? 0) + 1)
}

function statusTagType(passed?: boolean | null) {
  return passed ? 'success' : 'warning'
}

function issueDimensionLabel(issue: QAIssue) {
  return issue.related_dimension || issue.target_node_label || issue.target_node || '未定位维度'
}

function issueGroupKey(issue: QAIssue) {
  return issue.target_node || issue.target_node_label || issue.related_dimension || 'unknown_dimension'
}

function issueGroupTagType(severity?: string) {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'info'
}

const issueGroups = computed(() => {
  const groups = new Map<string, { key: string; label: string; issues: QAIssue[]; maxSeverity: string }>()
  const severityRank: Record<string, number> = { high: 3, medium: 2, low: 1 }
  for (const issue of props.qa?.issues || []) {
    const key = issueGroupKey(issue)
    const label = issueDimensionLabel(issue)
    const group = groups.get(key)
    if (group) {
      group.issues.push(issue)
      if ((severityRank[issue.severity] || 0) > (severityRank[group.maxSeverity] || 0)) {
        group.maxSeverity = issue.severity
      }
      continue
    }
    groups.set(key, { key, label, issues: [issue], maxSeverity: issue.severity })
  }
  return [...groups.values()].sort((a, b) => {
    const severityRankA = severityRank[a.maxSeverity] || 0
    const severityRankB = severityRank[b.maxSeverity] || 0
    if (severityRankA !== severityRankB) return severityRankB - severityRankA
    return a.label.localeCompare(b.label, 'zh-Hans-CN')
  })
})

watch(
  issueGroups,
  (groups) => {
    if (!props.qa || !groups.length) {
      activeIssueGroups.value = []
      issueGroupsInitializedForQa.value = props.qa?.id ?? null
      return
    }
    if (issueGroupsInitializedForQa.value !== props.qa.id) {
      activeIssueGroups.value = []
      issueGroupsInitializedForQa.value = props.qa.id
      return
    }
    const validKeys = new Set(groups.map((group) => group.key))
    activeIssueGroups.value = activeIssueGroups.value.filter((key) => validKeys.has(key))
  },
  { immediate: true },
)

watch(
  () => props.dimensionQaRoundGroups || [],
  (groups) => {
    if (!groups.length) {
      activeHistoryRounds.value = []
      historyRoundsInitialized.value = false
      return
    }
    if (!historyRoundsInitialized.value) {
      activeHistoryRounds.value = [groups[0]?.key || '']
      historyRoundsInitialized.value = true
      return
    }
    const validKeys = new Set(groups.map((group) => group.key))
    activeHistoryRounds.value = activeHistoryRounds.value.filter((key) => validKeys.has(key))
  },
  { immediate: true },
)
</script>

<template>
  <el-empty v-if="!qa && !qualitySummary" description="暂无 QA 结果" />
  <div v-else class="qa-panel">
    <div v-if="qualitySummary" class="qa-section">
      <div class="section-heading">
        <h3>最终报告结果</h3>
        <el-tag :type="qualitySummary.final_status === '通过' ? 'success' : 'warning'">
          {{ qualitySummary.final_status || '未通过' }}
        </el-tag>
      </div>
      <div class="qa-overview">
        <div class="overview-item">
          <span>最终结果</span>
          <strong>{{ qualitySummary.final_status || '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>最终分数</span>
          <strong>{{ qualitySummary.final_score ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>维度 QA 均分</span>
          <strong>{{ qualitySummary.dimension_avg ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>总结 QA 分数</span>
          <strong>{{ qualitySummary.finalizer_score ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>分数构成</span>
          <strong>{{ qualitySummary.dimension_weight ?? 0.7 }} / {{ qualitySummary.finalizer_weight ?? 0.3 }}</strong>
        </div>
      </div>
      <div v-if="qualitySummary.blockers?.length" class="target-list">
        <el-tag v-for="blocker in qualitySummary.blockers" :key="blocker" type="danger" effect="plain">
          {{ blocker }}
        </el-tag>
      </div>
    </div>

    <div v-if="qa" class="qa-section qa-card">
      <div class="section-heading">
        <h3>分析维度 QA</h3>
        <el-tag :type="statusTagType(qa.passed)">{{ qa.passed ? '通过' : '未通过' }}</el-tag>
      </div>
      <div class="qa-overview">
        <div class="overview-item">
          <span>检查范围</span>
          <strong>{{ qaScopeLabel }}</strong>
        </div>
        <div class="overview-item">
          <span>最新轮次分数</span>
          <strong>{{ qa.score ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>最新轮次结果</span>
          <strong>{{ qa.passed ? '通过' : '未通过' }}</strong>
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

      <div v-if="targetLabels.length" class="target-list">
        <el-tag v-for="node in targetLabels" :key="node" type="warning" effect="plain">
          {{ node }}
        </el-tag>
      </div>

      <el-table v-if="latestDimensionRows.length" :data="latestDimensionRows" border>
        <el-table-column label="维度">
          <template #default="{ row }">{{ row.dimension_label }}</template>
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
        <el-table-column label="来源轮次" width="120">
          <template #default="{ row }">第 {{ row.display_round }} 轮</template>
        </el-table-column>
        <el-table-column label="返工建议" min-width="140">
          <template #default="{ row }">{{ row.suggestion || '-' }}</template>
        </el-table-column>
      </el-table>

      <div v-if="revisionReasonItems.length && !qa.issues.length">
        <div class="section-title">返工原因</div>
        <ol class="reason-list">
          <li v-for="(reason, index) in revisionReasonItems" :key="`${index}-${reason}`">
            {{ reason }}
          </li>
        </ol>
      </div>

      <div v-if="issueGroups.length">
        <div class="section-title">维度问题</div>
        <el-collapse v-model="activeIssueGroups" class="issue-collapse">
          <el-collapse-item v-for="group in issueGroups" :key="group.key" :name="group.key">
            <template #title>
              <div class="issue-group-title">
                <strong>{{ group.label }}</strong>
                <el-tag :type="issueGroupTagType(group.maxSeverity)" size="small" effect="plain">
                  {{ issueSeverityLabel(group.maxSeverity) }}
                </el-tag>
                <span>{{ group.issues.length }} 个问题</span>
              </div>
            </template>
            <el-table :data="group.issues" border>
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
              <el-table-column label="建议" width="140">
                <template #default="{ row }">{{ row.suggested_action_label || issueActionLabel(row.suggested_action) }}</template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div v-if="dimensionQaRoundGroups?.length">
        <div class="section-title">每轮每维 QA 得分</div>
        <el-collapse v-model="activeHistoryRounds" class="qa-round-collapse">
          <el-collapse-item v-for="group in dimensionQaRoundGroups" :key="group.key" :name="group.key">
            <template #title>
              <div class="qa-round-title">
                <strong>第 {{ group.display_round }} 轮</strong>
                <el-tag :type="group.passed_count === group.total_count ? 'success' : 'warning'" size="small">
                  {{ group.passed_count }}/{{ group.total_count }} 通过
                </el-tag>
                <span>{{ group.qa_scope_label }}</span>
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
    </div>

    <div v-if="finalizerQa || qualitySummary" class="qa-section qa-card">
      <div class="section-heading">
        <h3>报告总结 Agent QA</h3>
        <el-tag :type="qualitySummary?.finalizer_grounding_status === '通过' || finalizerQa?.passed ? 'success' : 'warning'">
          {{ qualitySummary?.finalizer_grounding_status || (finalizerQa?.passed ? '通过' : '未通过') }}
        </el-tag>
      </div>
      <div class="qa-overview">
        <div class="overview-item">
          <span>总结 QA 结果</span>
          <strong>{{ qualitySummary?.finalizer_grounding_status || (finalizerQa?.passed ? '通过' : '未通过') }}</strong>
        </div>
        <div class="overview-item">
          <span>总结 QA 分数</span>
          <strong>{{ finalizerQa?.score ?? qualitySummary?.finalizer_score ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>通过门槛</span>
          <strong>{{ finalizerQa?.pass_threshold ?? qualitySummary?.finalizer_pass_threshold ?? '-' }}</strong>
        </div>
        <div class="overview-item">
          <span>内部轮次</span>
          <strong>第 {{ finalizerRound(finalizerQa?.revision_round) }} 轮</strong>
        </div>
      </div>
      <el-table v-if="finalizerIssues.length" :data="finalizerIssues" border>
        <el-table-column label="级别" width="110">
          <template #default="{ row }">
            <el-tag :type="severityType[row.severity] || 'info'" size="small">
              {{ issueSeverityLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="问题" />
      </el-table>
    </div>
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

.issue-collapse {
  border-top: 1px solid var(--el-border-color-light);
}

.qa-round-collapse {
  border-top: 1px solid var(--el-border-color-light);
}

.qa-round-title {
  display: grid;
  width: 100%;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.qa-round-title strong {
  color: var(--el-text-color-primary);
}

.qa-round-title span {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issue-group-title {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 10px;
}

.issue-group-title strong {
  overflow: hidden;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issue-group-title span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
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
