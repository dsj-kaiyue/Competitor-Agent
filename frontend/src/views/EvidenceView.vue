<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import EvidenceList from '@/components/EvidenceList.vue'
import { getTaskEvidence } from '@/api/analysisTaskApi'
import type { EvidenceItem } from '@/types/evidence'

const taskId = Number(useRoute().params.id)
const items = ref<EvidenceItem[]>([])
const competitor = ref('')
const sourceType = ref('')

const competitors = computed(() => Array.from(new Set(items.value.map((item) => item.competitor_name).filter(Boolean))) as string[])
const sourceTypes = computed(() => Array.from(new Set(items.value.map((item) => item.source_type).filter(Boolean))) as string[])

async function load() {
  const params: Record<string, string> = {}
  if (competitor.value) params.competitor_name = competitor.value
  if (sourceType.value) params.source_type = sourceType.value
  items.value = await getTaskEvidence(taskId, params)
}

onMounted(load)
</script>

<template>
  <main class="page">
    <section class="toolbar">
      <div>
        <h1>证据链</h1>
        <p>Evidence Chunk、来源 URL 与可信度</p>
      </div>
      <RouterLink :to="`/tasks/${taskId}`">
        <el-button>返回任务</el-button>
      </RouterLink>
    </section>

    <section class="filters">
      <el-select v-model="competitor" clearable placeholder="竞品" @change="load">
        <el-option v-for="name in competitors" :key="name" :label="name" :value="name" />
      </el-select>
      <el-select v-model="sourceType" clearable placeholder="来源类型" @change="load">
        <el-option v-for="type in sourceTypes" :key="type" :label="type" :value="type" />
      </el-select>
    </section>

    <EvidenceList :items="items" />
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

.toolbar {
  padding: 28px 0 8px;
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

  h1 {
    font-size: 28px;
  }
}
</style>
