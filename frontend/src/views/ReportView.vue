<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'
import ClaimList from '@/components/ClaimList.vue'
import ComparisonMatrixTable from '@/components/ComparisonMatrixTable.vue'
import ReportMarkdown from '@/components/ReportMarkdown.vue'
import { downloadTaskReport, getTaskClaims, getTaskQa, getTaskReportDetail } from '@/api/analysisTaskApi'
import type { ClaimItem } from '@/types/claim'
import type { ComparisonMatrix } from '@/types/comparisonMatrix'
import type { QAResult } from '@/types/qa'
import type { ReportEvidenceItem, ReportItem } from '@/types/report'

const taskId = Number(useRoute().params.id)
const report = ref<ReportItem | null>(null)
const qa = ref<QAResult | null>(null)
const claims = ref<ClaimItem[]>([])
const evidence = ref<ReportEvidenceItem[]>([])
const matrices = ref<ComparisonMatrix[]>([])
const exporting = ref(false)

const claimById = computed(() => new Map(claims.value.map((claim) => [claim.id, claim])))
const evidenceById = computed(() => new Map(evidence.value.map((item) => [item.id, item])))
const sections = computed(() => report.value?.report_json?.sections || [])
const qualitySummary = computed(() => report.value?.report_json?.quality_summary)
const dimensionQaScores = computed(() => report.value?.report_json?.dimension_qa_scores || [])
const qaIssues = computed(() => qa.value?.issues || [])

const severityType: Record<string, 'danger' | 'warning' | 'info'> = {
  high: 'danger',
  medium: 'warning',
  low: 'info',
}

const issueTypeLabels: Record<string, string> = {
  unsupported_claim: '证据缺失',
  weak_evidence: '证据较弱',
  schema_incomplete: '结构缺失',
  logic_gap: '逻辑缺口',
  writing_issue: '写作问题',
}

const actionLabels: Record<string, string> = {
  end: '无需返工',
  recollect: '重新收集资料',
  reanalyze: '重新分析',
  rewrite: '重写报告',
  ignore: '忽略',
}

function issueTypeLabel(type?: string) {
  return type ? issueTypeLabels[type] || type : '-'
}

function issueActionLabel(action?: string) {
  return action ? actionLabels[action] || action : '-'
}

onMounted(async () => {
  const [detail, qaResult, claimItems] = await Promise.all([
    getTaskReportDetail(taskId),
    getTaskQa(taskId),
    getTaskClaims(taskId),
  ])
  report.value = detail.report
  qa.value = detail.qa_result || qaResult
  claims.value = detail.claims?.length ? detail.claims : claimItems
  evidence.value = detail.evidence || []
  matrices.value = detail.matrices || []
})

async function handleExport(format: 'markdown' | 'pdf') {
  if (!report.value || exporting.value) {
    return
  }
  exporting.value = true
  try {
    await downloadTaskReport(taskId, format)
    ElMessage.success(format === 'pdf' ? 'PDF 导出已开始' : 'Markdown 导出已开始')
  } catch (error) {
    const message = error instanceof Error ? error.message : '导出失败'
    ElMessage.error(message)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>{{ report?.title || '分析报告' }}</h1>
        <p>报告与 Claim-Evidence 关联</p>
      </div>
      <div class="toolbar-actions">
        <el-dropdown :disabled="!report || exporting" @command="handleExport">
          <el-button type="primary" :loading="exporting">
            导出报告
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="markdown">Markdown 文件</el-dropdown-item>
              <el-dropdown-item command="pdf">PDF 文件</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <RouterLink :to="`/tasks/${taskId}`">
          <el-button>返回任务</el-button>
        </RouterLink>
      </div>
    </section>

    <el-empty v-if="!report" description="暂无报告" />
    <section v-if="report && qualitySummary" class="quality-section">
      <div class="quality-header">
        <h2>报告质量概览</h2>
        <el-tag :type="qualitySummary.final_status === '通过' ? 'success' : 'warning'">
          {{ qualitySummary.final_status || '未通过' }}
        </el-tag>
      </div>
      <div class="quality-grid">
        <div class="quality-item">
          <span>维度正文 QA</span>
          <strong>{{ qualitySummary.dimension_body_qa_status || '-' }}</strong>
        </div>
        <div class="quality-item">
          <span>总结溯源检查</span>
          <strong>{{ qualitySummary.finalizer_grounding_status || '-' }}</strong>
        </div>
        <div class="quality-item">
          <span>最终 QA 分数</span>
          <strong>{{ qualitySummary.final_score ?? '-' }}</strong>
        </div>
        <div class="quality-item">
          <span>分数构成</span>
          <strong>{{ qualitySummary.dimension_avg ?? '-' }} × 70% + {{ qualitySummary.finalizer_score ?? '-' }} × 30%</strong>
        </div>
      </div>
      <div v-if="qualitySummary.blockers?.length" class="quality-blockers">
        <el-tag v-for="blocker in qualitySummary.blockers" :key="blocker" type="danger" effect="plain">
          {{ blocker }}
        </el-tag>
      </div>
      <el-table v-if="dimensionQaScores.length" :data="dimensionQaScores" border>
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
      </el-table>
      <div class="quality-issues">
        <h3>QA 问题</h3>
        <el-empty v-if="!qaIssues.length" description="暂无 QA 问题" />
        <el-table v-else :data="qaIssues" border>
          <el-table-column label="级别" width="110">
            <template #default="{ row }">
              <el-tag :type="severityType[row.severity] || 'info'" size="small">
                {{ row.severity_label || row.severity || '-' }}
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
    </section>
    <section v-if="report && sections.length" class="report-json">
      <article v-for="section in sections" :key="section.section_id" class="report-section">
        <h2>{{ section.title }}</h2>
        <div v-for="paragraph in section.paragraphs" :key="paragraph.paragraph_id" class="paragraph-block">
          <p>{{ paragraph.text }}</p>
          <el-collapse class="provenance">
            <el-collapse-item
              :title="`查看依据：${paragraph.claim_ids?.length || 0} 条 Claim，${paragraph.evidence_ids?.length || 0} 条 Evidence`"
              :name="paragraph.paragraph_id"
            >
              <div class="provenance-grid">
                <div>
                  <h3>相关 Claim</h3>
                  <ul>
                    <li v-for="claimId in paragraph.claim_ids" :key="claimId">
                      <strong>#{{ claimId }}</strong>
                      <span>{{ claimById.get(claimId)?.claim_text || '未找到 Claim' }}</span>
                      <el-tag size="small" effect="plain">{{ claimById.get(claimId)?.confidence ?? '-' }}</el-tag>
                    </li>
                  </ul>
                </div>
                <div>
                  <h3>相关 Evidence</h3>
                  <ul>
                    <li v-for="evidenceId in paragraph.evidence_ids" :key="evidenceId">
                      <a :href="evidenceById.get(evidenceId)?.source_url" target="_blank" rel="noreferrer">
                        {{
                          evidenceById.get(evidenceId)?.source_title ||
                          evidenceById.get(evidenceId)?.source_url ||
                          `Evidence #${evidenceId}`
                        }}
                      </a>
                      <el-tag size="small">{{ evidenceById.get(evidenceId)?.source_type || '-' }}</el-tag>
                      <p>{{ evidenceById.get(evidenceId)?.chunk_text }}</p>
                    </li>
                  </ul>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </article>
    </section>
    <ReportMarkdown v-else-if="report" :markdown="report.content_markdown" />

    <section v-if="matrices.length" class="section">
      <h2>动态对比矩阵</h2>
      <ComparisonMatrixTable :matrices="matrices" />
    </section>

    <section class="section">
      <h2>结构化结论</h2>
      <ClaimList :items="claims" />
    </section>
  </main>
</template>

<style scoped>
.page,
.section {
  display: grid;
  gap: 22px;
}

.report-json,
.report-section,
.paragraph-block {
  display: grid;
  gap: 16px;
}

.report-section {
  padding: 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

.paragraph-block > p {
  margin: 0;
  color: var(--ca-ink);
  font-size: 17px;
  line-height: 1.72;
}

.provenance {
  border-top: 1px solid var(--el-border-color-lighter);
}

.provenance-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.provenance-grid ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding-left: 18px;
}

.provenance-grid li {
  line-height: 1.6;
}

.provenance-grid li span,
.provenance-grid li a {
  margin: 0 8px;
}

.provenance-grid li p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 0 8px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.quality-section {
  display: grid;
  gap: 16px;
  padding: 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

.quality-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.quality-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.quality-item {
  display: grid;
  gap: 4px;
  padding: 16px;
  border: 1px solid var(--ca-divider-soft);
  border-radius: 14px;
  background: var(--ca-pearl);
}

.quality-item span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.quality-item strong {
  color: var(--el-text-color-primary);
  font-size: 18px;
  font-weight: 600;
}

.quality-blockers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quality-issues {
  display: grid;
  gap: 10px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  color: var(--ca-ink);
  font-size: 34px;
  font-weight: 600;
  line-height: 1.14;
  letter-spacing: 0;
}

h2 {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

h3 {
  font-size: 17px;
  font-weight: 600;
}

p {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
}

.section {
  padding: 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

@media (max-width: 760px) {
  .quality-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .provenance-grid {
    grid-template-columns: 1fr;
  }

  .toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    width: 100%;
  }

  h1 {
    font-size: 28px;
  }
}
</style>
