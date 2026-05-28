<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'
import ClaimList from '@/components/ClaimList.vue'
import QaResultPanel from '@/components/QaResultPanel.vue'
import ReportMarkdown from '@/components/ReportMarkdown.vue'
import { downloadTaskReport, getTaskClaims, getTaskQa, getTaskReportDetail } from '@/api/analysisTaskApi'
import type { ClaimItem } from '@/types/claim'
import type { QAResult } from '@/types/qa'
import type { ReportEvidenceItem, ReportItem } from '@/types/report'

const taskId = Number(useRoute().params.id)
const report = ref<ReportItem | null>(null)
const qa = ref<QAResult | null>(null)
const claims = ref<ClaimItem[]>([])
const evidence = ref<ReportEvidenceItem[]>([])
const exporting = ref(false)

const claimById = computed(() => new Map(claims.value.map((claim) => [claim.id, claim])))
const evidenceById = computed(() => new Map(evidence.value.map((item) => [item.id, item])))
const sections = computed(() => report.value?.report_json?.sections || [])

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
        <p>报告、QA 与 Claim-Evidence 关联</p>
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
    <section v-else-if="sections.length" class="report-json">
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
    <ReportMarkdown v-else :markdown="report.content_markdown" />

    <section class="section">
      <h2>QA 结果</h2>
      <QaResultPanel :qa="qa" />
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
  gap: 18px;
}

.report-json,
.report-section,
.paragraph-block {
  display: grid;
  gap: 14px;
}

.report-section {
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.paragraph-block > p {
  margin: 0;
  line-height: 1.8;
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
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
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
}
</style>
