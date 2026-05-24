<script setup lang="ts">
import type { EvidenceItem } from '@/types/evidence'

defineProps<{ items: EvidenceItem[] }>()
</script>

<template>
  <el-table :data="items" border>
    <el-table-column prop="competitor_name" label="竞品" width="150" />
    <el-table-column prop="source_type" label="来源类型" width="150" />
    <el-table-column label="证据片段" min-width="360">
      <template #default="{ row }">
        <div class="chunk">{{ row.chunk_text }}</div>
        <a :href="row.source_url" target="_blank" rel="noopener">{{ row.source_title || row.source_url }}</a>
      </template>
    </el-table-column>
    <el-table-column prop="reliability_score" label="可信度" width="100" />
  </el-table>
</template>

<style scoped>
.chunk {
  margin-bottom: 6px;
  line-height: 1.55;
}
</style>
