<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import ClaimList from '@/components/ClaimList.vue'
import QaResultPanel from '@/components/QaResultPanel.vue'
import ReportMarkdown from '@/components/ReportMarkdown.vue'
import { getTaskClaims, getTaskQa, getTaskReport } from '@/api/analysisTaskApi'
import type { ClaimItem } from '@/types/claim'
import type { QAResult } from '@/types/qa'
import type { ReportItem } from '@/types/report'

const taskId = Number(useRoute().params.id)
const report = ref<ReportItem | null>(null)
const qa = ref<QAResult | null>(null)
const claims = ref<ClaimItem[]>([])

onMounted(async () => {
  ;[report.value, qa.value, claims.value] = await Promise.all([
    getTaskReport(taskId),
    getTaskQa(taskId),
    getTaskClaims(taskId),
  ])
})
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>{{ report?.title || '分析报告' }}</h1>
        <p>报告、QA 与 Claim-Evidence 关联</p>
      </div>
      <RouterLink :to="`/tasks/${taskId}`">
        <el-button>返回任务</el-button>
      </RouterLink>
    </section>

    <el-empty v-if="!report" description="暂无报告" />
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

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
