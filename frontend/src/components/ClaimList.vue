<script setup lang="ts">
import type { ClaimItem } from '@/types/claim'

defineProps<{ items: ClaimItem[] }>()
</script>

<template>
  <el-table :data="items" border>
    <el-table-column prop="competitor_name" label="竞品" width="150" />
    <el-table-column prop="dimension_label" label="分析维度" width="160">
      <template #default="{ row }">{{ row.dimension_label || row.dimension_key || row.claim_type || '-' }}</template>
    </el-table-column>
    <el-table-column prop="claim_type" label="类型" width="110" />
    <el-table-column prop="claim_text" label="结论" min-width="380" />
    <el-table-column label="证据" width="160">
      <template #default="{ row }">#{{ row.evidence_ids.join(', #') }}</template>
    </el-table-column>
  </el-table>
</template>
