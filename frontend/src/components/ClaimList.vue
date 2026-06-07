<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { ClaimItem } from '@/types/claim'

defineProps<{ items: ClaimItem[] }>()
</script>

<template>
  <el-table :data="items" border>
    <el-table-column prop="competitor_name" label="竞品" width="150" />
    <el-table-column prop="dimension_label" label="分析维度" width="160">
      <template #default="{ row }">{{ row.dimension_label || row.dimension_key || row.claim_type || '-' }}</template>
    </el-table-column>
    <el-table-column prop="claim_text" label="结论" min-width="380" />
    <el-table-column label="置信度" width="100">
      <template #default="{ row }">
        {{ row.confidence === null || row.confidence === undefined ? '-' : Number(row.confidence).toFixed(2) }}
      </template>
    </el-table-column>
    <el-table-column label="风险" width="90">
      <template #default="{ row }">{{ row.risk_level || '-' }}</template>
    </el-table-column>
    <el-table-column label="证据" min-width="160">
      <template #default="{ row }">
        <span v-if="!row.evidence_ids?.length">-</span>
        <div v-else class="evidence-tags">
          <RouterLink
            v-for="id in row.evidence_ids"
            :key="id"
            :to="`/tasks/${row.task_id}/evidence?evidence=${id}`"
            class="evidence-tag-wrapper"
          >
            <el-tag class="evidence-tag-link">#{{ id }}</el-tag>
          </RouterLink>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.evidence-tag-wrapper {
  text-decoration: none;
}

.evidence-tag-link {
  cursor: pointer;
  transition: all 0.2s;
}

.evidence-tag-link:hover {
  transform: translateY(-1px);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  filter: brightness(0.95);
}
</style>
