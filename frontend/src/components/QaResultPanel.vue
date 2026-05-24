<script setup lang="ts">
import type { QAResult } from '@/types/qa'

defineProps<{ qa: QAResult | null }>()
</script>

<template>
  <el-empty v-if="!qa" description="暂无 QA 结果" />
  <div v-else class="qa-panel">
    <el-result
      :icon="qa.passed ? 'success' : 'warning'"
      :title="qa.passed ? 'QA 通过' : 'QA 需要复核'"
      :sub-title="`评分：${qa.score ?? '-'}`"
    />
    <el-table v-if="qa.issues.length" :data="qa.issues" border>
      <el-table-column prop="severity" label="级别" width="110" />
      <el-table-column prop="type" label="类型" width="160" />
      <el-table-column prop="message" label="问题" />
      <el-table-column prop="suggested_action" label="建议" width="130" />
    </el-table>
  </div>
</template>

<style scoped>
.qa-panel {
  display: grid;
  gap: 16px;
}
</style>
