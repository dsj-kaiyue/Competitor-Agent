<script setup lang="ts">
import type { QAResult } from '@/types/qa'

defineProps<{ qa: QAResult | null }>()

const severityType: Record<string, 'danger' | 'warning' | 'info'> = {
  high: 'danger',
  medium: 'warning',
  low: 'info',
}
</script>

<template>
  <el-empty v-if="!qa" description="暂无 QA 结果" />
  <div v-else class="qa-panel">
    <el-result
      :icon="qa.passed ? 'success' : 'warning'"
      :title="qa.passed ? 'QA 通过' : 'QA 需要复核'"
      :sub-title="`评分：${qa.score ?? '-'}`"
    />
    <div class="qa-meta">
      <el-tag :type="qa.next_action && qa.next_action !== 'end' ? 'warning' : 'success'">
        next_action: {{ qa.next_action || 'end' }}
      </el-tag>
      <el-tag effect="plain">revision_round: {{ qa.revision_round ?? 0 }}</el-tag>
      <el-tag v-for="node in qa.target_nodes || []" :key="node" type="warning" effect="plain">
        {{ node }}
      </el-tag>
    </div>
    <p v-if="qa.revision_reason" class="reason">{{ qa.revision_reason }}</p>
    <el-table v-if="qa.issues.length" :data="qa.issues" border>
      <el-table-column label="级别" width="110">
        <template #default="{ row }">
          <el-tag :type="severityType[row.severity] || 'info'" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="160" />
      <el-table-column prop="message" label="问题" />
      <el-table-column prop="related_dimension" label="维度" width="120" />
      <el-table-column prop="suggested_action" label="建议" width="130" />
    </el-table>
  </div>
</template>

<style scoped>
.qa-panel {
  display: grid;
  gap: 16px;
}

.qa-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.reason {
  margin: 0;
  color: var(--el-text-color-secondary);
}
</style>
