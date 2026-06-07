<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import EvidenceList from '@/components/EvidenceList.vue'
import { getTaskClaims, getTaskEvidence } from '@/api/analysisTaskApi'
import type { ClaimItem } from '@/types/claim'
import type { EvidenceItem } from '@/types/evidence'

const taskId = Number(useRoute().params.id)
const items = ref<EvidenceItem[]>([])
const claims = ref<ClaimItem[]>([])
const dimension = ref('')
const competitor = ref('')
const sourceType = ref('')
const claimTableCollapsed = ref(false)
const evidenceTableCollapsed = ref(false)

const evidenceById = computed(() => new Map(items.value.map((item) => [item.id, item])))
const dimensions = computed(() =>
  Array.from(new Set(claims.value.map((claim) => claimDimension(claim)).filter(Boolean))) as string[],
)
const competitors = computed(
  () =>
    Array.from(
      new Set([
        ...items.value.map((item) => item.competitor_name).filter(Boolean),
        ...claims.value.map((claim) => claim.competitor_name).filter(Boolean),
      ]),
    ) as string[],
)
const sourceTypes = computed(() => Array.from(new Set(items.value.map((item) => item.source_type).filter(Boolean))) as string[])

const filteredClaims = computed(() =>
  claims.value.filter((claim) => {
    if (dimension.value && claimDimension(claim) !== dimension.value) return false
    if (competitor.value && claim.competitor_name !== competitor.value) return false
    if (sourceType.value) {
      return claim.evidence_ids.some((id) => evidenceById.value.get(id)?.source_type === sourceType.value)
    }
    return true
  }),
)

const filteredEvidenceIds = computed(() => new Set(filteredClaims.value.flatMap((claim) => claim.evidence_ids)))
const hasActiveFilter = computed(() => Boolean(dimension.value || competitor.value || sourceType.value))
const filteredEvidence = computed(() => {
  if (!hasActiveFilter.value) return items.value
  return items.value.filter((item) => {
    if (!filteredEvidenceIds.value.has(item.id)) return false
    if (competitor.value && item.competitor_name !== competitor.value) return false
    if (sourceType.value && item.source_type !== sourceType.value) return false
    return true
  })
})

async function load() {
  items.value = await getTaskEvidence(taskId)
}

async function loadClaims() {
  claims.value = await getTaskClaims(taskId)
}

function evidenceIdsText(evidenceIds: number[]) {
  return evidenceIds.length ? evidenceIds.map((id) => `#${id}`).join(', ') : '-'
}

function claimDimension(claim: ClaimItem) {
  return claim.dimension_label || claim.dimension_key || claim.claim_type || ''
}

onMounted(async () => {
  await Promise.all([load(), loadClaims()])
})
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>结论与证据</h1>
        <p>查看分析结论及其关联的原始来源与参考片段。</p>
      </div>
      <RouterLink :to="`/tasks/${taskId}`">
        <el-button>返回任务</el-button>
      </RouterLink>
    </section>

    <section class="filters">
      <el-select v-model="dimension" clearable placeholder="分析维度">
        <el-option v-for="name in dimensions" :key="name" :label="name" :value="name" />
      </el-select>
      <el-select v-model="competitor" clearable placeholder="竞品">
        <el-option v-for="name in competitors" :key="name" :label="name" :value="name" />
      </el-select>
      <el-select v-model="sourceType" clearable placeholder="来源">
        <el-option v-for="type in sourceTypes" :key="type" :label="type" :value="type" />
      </el-select>
    </section>

    <section class="evidence-workspace">
      <section class="claim-panel">
        <div class="claim-panel-header">
          <h2>Claim 结论</h2>
          <div class="panel-actions">
            <span>{{ filteredClaims.length }} 条</span>
            <el-button
              class="collapse-btn"
              circle
              :icon="claimTableCollapsed ? ArrowRight : ArrowDown"
              @click="claimTableCollapsed = !claimTableCollapsed"
            />
          </div>
        </div>
        <el-table v-show="!claimTableCollapsed" :data="filteredClaims" border>
          <el-table-column label="编号" width="76" fixed>
            <template #default="{ row }">#{{ row.id }}</template>
          </el-table-column>
          <el-table-column label="分析维度" min-width="130">
            <template #default="{ row }">{{ row.dimension_label || row.dimension_key || row.claim_type || '-' }}</template>
          </el-table-column>
          <el-table-column label="竞品" min-width="120">
            <template #default="{ row }">{{ row.competitor_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="claim_text" label="结论内容" min-width="260" />
          <el-table-column label="关联证据编号" min-width="150">
            <template #default="{ row }">{{ evidenceIdsText(row.evidence_ids) }}</template>
          </el-table-column>
        </el-table>
      </section>
      <div class="evidence-panel">
        <div class="claim-panel-header">
          <h2>底层证据</h2>
          <div class="panel-actions">
            <span>{{ filteredEvidence.length }} 条</span>
            <el-button
              class="collapse-btn"
              circle
              :icon="evidenceTableCollapsed ? ArrowRight : ArrowDown"
              @click="evidenceTableCollapsed = !evidenceTableCollapsed"
            />
          </div>
        </div>
        <EvidenceList v-show="!evidenceTableCollapsed" :items="filteredEvidence" />
      </div>
    </section>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  gap: 22px;
}

.toolbar,
.filters {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.filters {
  justify-content: flex-start;
  padding: 18px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

.filters :deep(.el-select) {
  flex: 1;
  min-width: 220px;
}

.toolbar {
  padding: 28px 0 8px;
}

.evidence-workspace {
  display: grid;
  gap: 18px;
}

.evidence-panel,
.claim-panel {
  min-width: 0;
}

.claim-panel {
  display: grid;
  gap: 12px;
}

.claim-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.claim-panel-header h2 {
  margin: 0;
  color: var(--ca-ink);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0;
}

.claim-panel-header span {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.collapse-btn {
  width: 28px;
  height: 28px;
  padding: 0;
}

h1,
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

p {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 17px;
}

@media (max-width: 760px) {
  .toolbar,
  .filters {
    align-items: flex-start;
    flex-direction: column;
  }

  .evidence-workspace {
    grid-template-columns: 1fr;
  }

  h1 {
    font-size: 28px;
  }
}
</style>
