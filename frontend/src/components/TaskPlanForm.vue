<script setup lang="ts">
import type { TaskPlan } from '@/types/taskPlan'

const model = defineModel<TaskPlan>({ required: true })

function addCompetitor() {
  model.value.competitors.push('')
}

function addDimension() {
  model.value.analysis_dimensions.push('')
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
    <el-row :gutter="16">
      <el-col :span="8">
        <el-form-item label="报告深度">
          <el-segmented v-model="model.report_depth" :options="['simple', 'standard', 'deep']" />
        </el-form-item>
      </el-col>
      <el-col :span="8">
        <el-form-item label="输出语言">
          <el-input v-model="model.output_language" />
        </el-form-item>
      </el-col>
      <el-col :span="8">
        <el-form-item label="自动发现竞品">
          <el-switch v-model="model.auto_discover_competitors" />
        </el-form-item>
      </el-col>
    </el-row>
    <el-form-item label="竞品列表">
      <div class="chip-editor">
        <el-input
          v-for="(_, index) in model.competitors"
          :key="index"
          v-model="model.competitors[index]"
          class="chip-input"
        />
        <el-button @click="addCompetitor">添加</el-button>
      </div>
    </el-form-item>
    <el-form-item label="分析维度">
      <div class="chip-editor">
        <el-input
          v-for="(_, index) in model.analysis_dimensions"
          :key="index"
          v-model="model.analysis_dimensions[index]"
          class="chip-input"
        />
        <el-button @click="addDimension">添加</el-button>
      </div>
    </el-form-item>
    <el-form-item label="数据来源">
      <el-checkbox-group v-model="model.data_sources">
        <el-checkbox-button label="official_website" />
        <el-checkbox-button label="pricing_page" />
        <el-checkbox-button label="docs" />
        <el-checkbox-button label="blog" />
        <el-checkbox-button label="news" />
        <el-checkbox-button label="reviews" />
      </el-checkbox-group>
    </el-form-item>
  </el-form>
</template>

<style scoped>
.task-plan-form {
  width: 100%;
}

.chip-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.chip-input {
  width: 190px;
}
</style>
