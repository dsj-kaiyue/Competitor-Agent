<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAnalysisTasks } from '@/api/analysisTaskApi'
import type { AnalysisTaskHistoryItem } from '@/types/analysisTask'

const tasks = ref<AnalysisTaskHistoryItem[]>([])
const loading = ref(false)
const errorMessage = ref('')

const hasTasks = computed(() => tasks.value.length > 0)

function statusTagType(status: string) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'queued') return 'warning'
  if (status === 'running') return 'primary'
  return 'info'
}

function nodeStatusCount(task: AnalysisTaskHistoryItem, status: string) {
  return task.nodes.filter((node) => node.status === status).length
}

async function loadHistory() {
  loading.value = true
  errorMessage.value = ''
  try {
    tasks.value = await getAnalysisTasks({ limit: 100 })
  } catch (error) {
    console.error(error)
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <main v-loading="loading" class="page">
    <section class="toolbar">
      <div>
        <h1>历史分析记录</h1>
        <p>查看过往任务、Agent 节点状态、报告和证据链。</p>
      </div>
      <div class="actions">
        <el-button @click="loadHistory">刷新</el-button>
        <RouterLink to="/">
          <el-button type="primary">新建分析</el-button>
        </RouterLink>
      </div>
    </section>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />

    <el-empty v-if="!loading && !hasTasks" description="暂无历史分析记录" />

    <section v-else class="task-list">
      <article v-for="task in tasks" :key="task.id" class="task-card">
        <div class="task-main">
          <div class="task-title">
            <strong>{{ task.topic }}</strong>
            <el-tag :type="statusTagType(task.status)" effect="plain">{{ task.status }}</el-tag>
          </div>
          <p>{{ task.user_input }}</p>
          <div class="meta">
            <span>#{{ task.id }}</span>
            <span>{{ task.industry || '未设置行业' }}</span>
            <span>{{ task.created_at }}</span>
          </div>
        </div>

        <div class="node-summary">
          <el-tag size="small" type="success">成功 {{ nodeStatusCount(task, 'success') }}</el-tag>
          <el-tag size="small" type="primary">运行 {{ nodeStatusCount(task, 'running') }}</el-tag>
          <el-tag size="small" type="warning">等待 {{ nodeStatusCount(task, 'pending') + nodeStatusCount(task, 'queued') }}</el-tag>
          <el-tag size="small" type="danger">失败 {{ nodeStatusCount(task, 'failed') }}</el-tag>
        </div>

        <div class="node-strip">
          <el-tooltip
            v-for="node in task.nodes"
            :key="node.id"
            :content="`${node.node_name}：${node.status}`"
            placement="top"
          >
            <span class="node-dot" :class="node.status" />
          </el-tooltip>
        </div>

        <div class="card-actions">
          <RouterLink :to="`/tasks/${task.id}`">
            <el-button>节点详情</el-button>
          </RouterLink>
          <RouterLink :to="`/tasks/${task.id}/report`">
            <el-button type="primary">报告</el-button>
          </RouterLink>
          <RouterLink :to="`/tasks/${task.id}/evidence`">
            <el-button>证据链</el-button>
          </RouterLink>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  gap: 18px;
}

.toolbar,
.task-title,
.card-actions,
.actions,
.node-summary {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar {
  justify-content: space-between;
}

.actions,
.card-actions,
.node-summary {
  flex-wrap: wrap;
}

.task-list {
  display: grid;
  gap: 12px;
}

.task-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: #fff;
}

.task-main {
  display: grid;
  gap: 8px;
}

.task-title {
  justify-content: space-between;
}

.task-title strong {
  min-width: 0;
  overflow: hidden;
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-main p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--el-text-color-regular);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.node-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18px, 1fr));
  gap: 6px;
}

.node-dot {
  display: block;
  height: 8px;
  border-radius: 999px;
  background: #c0c4cc;
}

.node-dot.running {
  background: #409eff;
}

.node-dot.success {
  background: #67c23a;
}

.node-dot.failed {
  background: #f56c6c;
}

.node-dot.queued,
.node-dot.pending {
  background: #e6a23c;
}

h1,
p {
  margin: 0;
}

h1 {
  font-size: 24px;
}

.toolbar p {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 760px) {
  .toolbar,
  .task-title {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
