<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getAnalysisTasks } from '@/api/analysisTaskApi'
import { getUsers } from '@/api/userApi'
import { useAuthStore } from '@/stores/authStore'
import type { AnalysisTaskHistoryItem } from '@/types/analysisTask'
import type { User } from '@/types/user'

const route = useRoute()
const tasks = ref<AnalysisTaskHistoryItem[]>([])
const users = ref<User[]>([])
const loading = ref(false)
const errorMessage = ref('')
const auth = useAuthStore()

const routeUserId = computed(() => {
  const queryId = Number(route.query.userId)
  return !isNaN(queryId) && queryId > 0 ? queryId : undefined
})

const hasTasks = computed(() => tasks.value.length > 0)
const targetUser = computed(() => users.value.find((u) => u.id === routeUserId.value))
const pageTitle = computed(() => {
  if (auth.isAdmin && routeUserId.value && targetUser.value) {
    return `${targetUser.value.username} 的历史记录`
  }
  return '历史分析记录'
})

function statusTagType(status: string) {
  if (status === 'success') return 'success'
  if (['failed', 'canceled', 'cancel_requested'].includes(status)) return 'danger'
  if (['queued', 'paused', 'pause_requested'].includes(status)) return 'warning'
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
    tasks.value = await getAnalysisTasks({
      limit: 100,
      user_id: auth.isAdmin ? routeUserId.value : undefined,
    })
  } catch (error) {
    console.error(error)
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

async function loadInitialData() {
  if (auth.isAdmin) {
    users.value = await getUsers()
  }
  await loadHistory()
}

watch(routeUserId, loadHistory)
onMounted(loadInitialData)
</script>

<template>
  <main v-loading="loading" class="page">
    <section class="toolbar">
      <div>
        <h1>{{ pageTitle }}</h1>
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
            <span v-if="auth.isAdmin">所属用户：{{ task.owner_username || '未分配' }}</span>
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
  gap: 22px;
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
  padding: 28px 0 12px;
}

.actions,
.card-actions,
.node-summary {
  flex-wrap: wrap;
}

.task-list {
  display: grid;
  gap: 14px;
}

.task-card {
  display: grid;
  gap: 14px;
  padding: 22px 24px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
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
  color: var(--ca-ink);
  font-size: 21px;
  font-weight: 600;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-main p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--el-text-color-regular);
  font-size: 17px;
  line-height: 1.47;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
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
  background: #d2d2d7;
}

.node-dot.running {
  background: var(--ca-primary);
}

.node-dot.success {
  background: #67c23a;
}

.node-dot.failed {
  background: #f56c6c;
}

.node-dot.canceled,
.node-dot.cancel_requested {
  background: #f56c6c;
}

.node-dot.queued,
.node-dot.pending,
.node-dot.paused,
.node-dot.pause_requested {
  background: #e6a23c;
}

h1,
p {
  margin: 0;
}

h1 {
  color: var(--ca-ink);
  font-size: 40px;
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: 0;
}

.toolbar p {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 21px;
  line-height: 1.35;
}

@media (max-width: 760px) {
  .toolbar,
  .task-title {
    align-items: flex-start;
    flex-direction: column;
  }

  h1 {
    font-size: 30px;
  }

  .toolbar p {
    font-size: 17px;
  }
}
</style>
