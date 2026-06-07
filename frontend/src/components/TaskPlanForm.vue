<script setup lang="ts">
import type { TaskPlan } from '@/types/taskPlan'

const model = defineModel<TaskPlan>({ required: true })

function addCompetitor() {
  model.value.competitors.push('')
}

function removeCompetitor(index: number) {
  model.value.competitors.splice(index, 1)
}

function addDimension() {
  model.value.analysis_dimensions.push('')
}

function removeDimension(index: number) {
  model.value.analysis_dimensions.splice(index, 1)
}
</script>

<template>
  <el-form class="task-plan-form" label-position="top">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="分析主题">
          <el-input v-model="model.topic" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="行业领域">
          <el-input v-model="model.industry" />
        </el-form-item>
      </el-col>
    </el-row>
    <el-form-item label="竞品列表">
      <div class="chip-editor">
        <div v-for="(_, index) in model.competitors" :key="index" class="chip-row">
          <el-input v-model="model.competitors[index]" class="chip-input" />
          <el-button type="danger" plain @click="removeCompetitor(index)">删除</el-button>
        </div>
        <el-button class="add-button" @click="addCompetitor">添加</el-button>
      </div>
    </el-form-item>
    <el-form-item label="分析维度">
      <div class="chip-editor">
        <div v-for="(_, index) in model.analysis_dimensions" :key="index" class="chip-row">
          <el-input v-model="model.analysis_dimensions[index]" class="chip-input" />
          <el-button type="danger" plain @click="removeDimension(index)">删除</el-button>
        </div>
        <el-button class="add-button" @click="addDimension">添加</el-button>
      </div>
    </el-form-item>
  </el-form>
</template>

<style scoped>
.task-plan-form {
  width: 100%;
}

.task-plan-form :deep(.el-form-item__label) {
  color: var(--ca-muted-strong);
  font-size: 14px;
  font-weight: 600;
}

.chip-editor {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  width: 100%;
}

.chip-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--ca-divider-soft);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-pearl);
}

.chip-input {
  min-width: 0;
  flex: 1;
}

.add-button {
  height: 48px;
  border-radius: var(--ca-radius-lg);
}

@media (max-width: 760px) {
  .task-plan-form :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
