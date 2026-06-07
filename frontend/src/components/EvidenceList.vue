<script setup lang="ts">
import type { EvidenceItem } from '@/types/evidence'

const props = defineProps<{ 
  items: EvidenceItem[]
  highlightId?: number | null
}>()

function getRowClassName({ row }: { row: EvidenceItem }) {
  const classes = [`evidence-row-${row.id}`]
  if (props.highlightId && row.id === props.highlightId) {
    classes.push('highlight-row-active')
  }
  return classes.join(' ')
}
</script>

<template>
  <el-table :data="items" border :row-class-name="getRowClassName">
    <el-table-column label="证据编号" width="100">
      <template #default="{ row }">#{{ row.id }}</template>
    </el-table-column>
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

<style>
.el-table .highlight-row-active {
  --el-table-tr-bg-color: var(--el-color-primary-light-8);
  transition: background-color 0.3s;
}
</style>
