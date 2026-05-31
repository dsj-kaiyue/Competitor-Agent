<script setup lang="ts">
import type { CompetitorProfile, ProfileFieldData } from '@/types/competitorProfile'

defineProps<{
  profiles: CompetitorProfile[]
}>()

function formatValue(data?: ProfileFieldData) {
  if (!data || data.value === null || data.value === undefined) {
    return data?.missing_reason || '暂无证据'
  }
  return Array.isArray(data.value) ? data.value.join('；') : data.value
}
</script>

<template>
  <div class="profile-grid">
    <article v-for="profile in profiles" :key="profile.id" class="profile-card">
      <header>
        <h3>{{ profile.competitor_name }}</h3>
        <el-tag size="small" effect="plain">{{ profile.profile_schema_json.fields.length }} 个维度</el-tag>
      </header>
      <dl>
        <template v-for="field in profile.profile_schema_json.fields" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd>
            <p>{{ formatValue(profile.profile_data_json[field.key]) }}</p>
            <div class="field-meta">
              <span>Claim {{ profile.profile_data_json[field.key]?.claim_ids?.length || 0 }}</span>
              <span>Evidence {{ profile.profile_data_json[field.key]?.evidence_ids?.length || 0 }}</span>
              <span>置信度 {{ profile.profile_data_json[field.key]?.confidence ?? 0 }}</span>
            </div>
          </dd>
        </template>
      </dl>
    </article>
  </div>
</template>

<style scoped>
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.profile-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: #fff;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

h3,
p,
dl {
  margin: 0;
}

dl {
  display: grid;
  gap: 10px;
}

dt {
  color: var(--el-text-color-primary);
  font-weight: 700;
}

dd {
  display: grid;
  gap: 6px;
  margin: 0;
  color: var(--el-text-color-secondary);
  line-height: 1.65;
}

.field-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
