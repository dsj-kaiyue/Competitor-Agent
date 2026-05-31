<script setup lang="ts">
import type { ComparisonMatrix, MatrixValue } from '@/types/comparisonMatrix'

defineProps<{
  matrices: ComparisonMatrix[]
}>()

function formatSummary(value?: MatrixValue) {
  if (!value || value.summary === null || value.summary === undefined) {
    return '暂无证据'
  }
  return Array.isArray(value.summary) ? value.summary.join('；') : value.summary
}
</script>

<template>
  <div class="matrix-stack">
    <section v-for="matrix in matrices" :key="matrix.id" class="matrix-section">
      <h3>{{ matrix.title }}</h3>
      <el-table :data="matrix.matrix_data_json.rows" border>
        <el-table-column prop="label" label="维度" fixed width="150" />
        <el-table-column
          v-for="column in matrix.matrix_schema_json.columns"
          :key="column"
          :label="column"
          min-width="220"
        >
          <template #default="{ row }">
            <div class="matrix-cell">
              <p>{{ formatSummary(row.values[column]) }}</p>
              <span>Claim {{ row.values[column]?.claim_ids?.length || 0 }} · Evidence {{ row.values[column]?.evidence_ids?.length || 0 }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.matrix-stack,
.matrix-section {
  display: grid;
  gap: 12px;
}

h3,
p {
  margin: 0;
}

.matrix-cell {
  display: grid;
  gap: 6px;
  line-height: 1.6;
}

.matrix-cell span {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
